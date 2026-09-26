"""复盘师 Agent：周报洞察（工具循环）与周三小结（单次调用）。

与教练的架构对比（有意为之，见 ADR-0002/笔记 06）：
- 教练有"缺信息提前结束"的分叉 → 用 LangGraph 图；
- 复盘师是纯线性"拿数据→写报告" → 不上图，直接 async 函数 + 工具循环。
  Agent 性来自工具循环本身（钻哪层数据由模型临场决定），不是来自外面包一层图。

写入纪律：submit_report 是唯一落库口（校验先行），产物必须人可读；
历史统计快照随报告存档（data_snapshot），保证当时口径可复现。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastmcp import Client, FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import AssistantResult, LLMBackend
from app.core.time import today_cn
from app.domain.enums import NotificationType, TaskStatus
from app.repositories.report import WeeklyReportRepository
from app.repositories.stats import StatsRepository
from app.services.push import notify_and_push
from app.services.stats import StatsService, _monday_of

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 5

_REVIEWER_SYSTEM_PROMPT = (
    "你是 GrowthCrew 的复盘师，为用户写本周成长周报。"
    "规则：1) 先调用 get_week_stats 了解整体完成情况与 streak；"
    "2) 若有跳过记录，调用 get_skip_reasons 和 get_hour_patterns 钻取原因；"
    "3) 调用 submit_report 提交周报。"
    "写作要求：简体中文；先讲事实（完成率/亮点），再给 1-2 条"
    "『用户自己可能没意识到的』具体洞察（结合卡因与时段），最后给下周可执行建议；"
    "语气温和鼓励，禁止指责式表述；不要编造数据；标题不超过 20 字。"
)

_MIDWEEK_SYSTEM_PROMPT = (
    "你是 GrowthCrew 的复盘师，写一段不超过 80 字的周三半周小结。"
    "语气温和；基于给定数据，先肯定已完成的部分，再给一句可执行调整；禁止编造。"
)


class ReviewerError(Exception):
    """复盘师未能产出有效结果。"""


@dataclass
class ReviewerContext:
    session: AsyncSession
    user_id: int
    week_start: date
    report_id: int | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    title: str = ""


def build_reviewer_tools(ctx: ReviewerContext) -> FastMCP:
    mcp = FastMCP("reviewer")

    @mcp.tool
    async def get_week_stats() -> dict[str, Any]:
        """本周完成统计：完成数/总数/完成率、有活动天数（完成或跳过）。"""
        stats = StatsService(ctx.session)
        trends = await stats.trends(ctx.user_id, weeks=1)
        points = trends.weeks
        if points:
            point = points[0]
            payload = {
                "done": point.done,
                "total": point.total,
                "rate": point.rate,
            }
        else:
            payload = {"done": 0, "total": 0, "rate": 0.0}
        stats_repo = StatsRepository(ctx.session)
        rows = await stats_repo.daily_status_counts(
            ctx.user_id, ctx.week_start, ctx.week_start + timedelta(days=6)
        )
        # 按日期去重、只算有实际动作（完成或跳过）的天，排除纯排程日
        active_dates = {
            row_date
            for row_date, status, _ in rows
            if status in (TaskStatus.DONE, TaskStatus.SKIPPED)
        }
        payload["days_with_activity"] = len(active_dates)
        ctx.snapshot["week_stats"] = payload
        return payload

    @mcp.tool
    async def get_skip_reasons() -> dict[str, Any]:
        """本周（周一至今）跳过任务的卡因分布（分心/太难/疲劳/被打断）。"""
        stats = StatsService(ctx.session)
        window = (today_cn() - ctx.week_start).days + 1  # 周界对齐：从周一起算
        result = await stats.skip_reasons(ctx.user_id, window_days=window)
        payload = {
            "items": [
                {"reason": item.reason, "count": item.count, "pct": item.pct}
                for item in result.items
            ]
        }
        ctx.snapshot["skip_reasons"] = payload
        return payload

    @mcp.tool
    async def get_hour_patterns() -> dict[str, Any]:
        """本周（周一至今）完成/跳过的时段分布（24 小时直方图，北京时间）。"""
        stats = StatsService(ctx.session)
        window = (today_cn() - ctx.week_start).days + 1
        result = await stats.hours(ctx.user_id, window_days=window)
        payload = {
            "completion_hours": result.completion_hours,
            "skip_hours": result.skip_hours,
        }
        ctx.snapshot["hour_patterns"] = payload
        return payload

    @mcp.tool
    async def submit_report(title: str, content: str) -> dict[str, Any]:
        """提交周报（校验通过后落库，并给用户发一条周报通知）。"""
        if ctx.report_id is not None:
            return {"report_id": ctx.report_id, "duplicate": True}
        if "week_stats" not in ctx.snapshot:
            return {"error": "请先调用 get_week_stats 获取本周数据再提交"}
        title = title.strip()[:195]  # 留余量给通知前缀，防 PG VARCHAR(200) 溢出
        content = content.strip()
        if not title:
            return {"error": "标题不能为空"}
        if len(content) < 30:
            return {"error": "周报正文太短（至少 30 字），请补充洞察后重新提交"}
        if len(content) > 5000:
            return {"error": "周报正文过长（最多 5000 字）"}

        repo = WeeklyReportRepository(ctx.session)
        report = await repo.upsert(
            user_id=ctx.user_id,
            week_start=ctx.week_start,
            title=title,
            content=content,
            data_snapshot=ctx.snapshot,
        )
        ctx.report_id = report.id
        ctx.title = title
        return {"report_id": report.id, "status": "已生成"}

    return mcp


class ReviewerAgent:
    def __init__(self, session: AsyncSession, backend: LLMBackend) -> None:
        self._session = session
        self._backend = backend

    async def run_weekly(self, user_id: int, week_start: date | None = None) -> dict[str, Any]:
        """生成周报：工具循环钻取数据 → 落库。返回报告字典。"""
        from app.core.time import today_cn

        start = week_start or _monday_of(today_cn())
        ctx = ReviewerContext(session=self._session, user_id=user_id, week_start=start)
        mcp = build_reviewer_tools(ctx)

        user_content = f"请为用户生成本周（周起始 {start.isoformat()}）的成长周报。"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _REVIEWER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        async with Client(mcp) as client:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema,
                    },
                }
                for t in await client.list_tools()
            ]
            for _ in range(_MAX_TOOL_ROUNDS):
                result: AssistantResult = await self._backend.complete(messages, tools)
                if not result.tool_calls:
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content,
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": c.name,
                                    "arguments": json.dumps(c.arguments, ensure_ascii=False),
                                },
                            }
                            for c in result.tool_calls
                        ],
                    }
                )
                for call in result.tool_calls:
                    try:
                        tool_result = await client.call_tool(call.name, call.arguments)
                        data: Any = getattr(tool_result, "data", None)
                        if data is None:
                            data = {"error": "工具无结构化返回"}
                    except Exception:
                        logger.exception("工具 %s 执行失败", call.name)
                        data = {"error": "工具执行失败，请检查参数后重试"}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(data, ensure_ascii=False),
                        }
                    )
                if ctx.report_id is not None:
                    break

        if ctx.report_id is None:
            raise ReviewerError("复盘师未能在限定轮次内产出周报")

        await notify_and_push(
            self._session,
            user_id,
            NotificationType.WEEKLY_REPORT,
            f"本周周报：{ctx.title[:30]}",
            "复盘师已生成本周成长周报，去看看它发现了什么。",
        )
        return {"report_id": ctx.report_id, "title": ctx.title}

    async def run_midweek(self, user_id: int) -> str:
        """周三小结：单次调用（数据内联），返回小结文案并写通知。"""
        from app.services.today import TodayService

        stats = StatsService(self._session)
        trends = await stats.trends(user_id, weeks=1)
        point = trends.weeks[0] if trends.weeks else None
        today_data = await TodayService(self._session).get(user_id)
        data_block = (
            f"本周至今：完成 {point.done if point else 0}/{point.total if point else 0}"
            f"（完成率 {point.rate if point else 0}%）；连续打卡 {today_data.streak} 天；"
            f"今日剩余待办 {sum(1 for t in today_data.tasks if t.status == 'todo')} 件。"
        )
        messages = [
            {"role": "system", "content": _MIDWEEK_SYSTEM_PROMPT},
            {"role": "user", "content": data_block},
        ]
        result = await self._backend.complete(messages)
        text = result.content.strip()
        if not text:
            raise ReviewerError("模型未返回小结内容")
        await notify_and_push(
            self._session, user_id, NotificationType.MIDWEEK_BRIEF, "周三小结", text
        )
        return text
