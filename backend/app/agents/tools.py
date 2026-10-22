"""教练 Agent 的工具集（FastMCP 注册，进程内调用）。

工具 = Agent 的手：只调 repository 层，与前端按钮同一条写入路径；
submit_proposal 是唯一的计划写入口（草稿态 + 提案审计），审批后才生效。
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scheduler import SubjectAllocation, next_monday
from app.agents.scheduler import schedule_week as run_scheduler
from app.core.time import today_cn
from app.domain.enums import PlanStatus, ProposalStatus
from app.models.goal import Goal
from app.models.plan import PlanProposal, WeeklyPlan
from app.models.report import WeeklyReport
from app.repositories.plan import (
    PlanProposalRepository,
    TaskRepository,
    WeeklyPlanRepository,
)
from app.services.stats import StatsService


@dataclass
class PlannerContext:
    """一次导入运行的可变状态（工具与图节点共享）。"""

    session: AsyncSession
    user_id: int
    goal: Goal
    proposal_id: int | None = None
    plan_id: int | None = None
    last_schedule: dict[str, Any] | None = None
    summary: str = ""
    parsed_subjects: list[dict[str, Any]] = field(default_factory=list)


def build_planner_tools(ctx: PlannerContext) -> FastMCP:
    mcp = FastMCP("planner")

    @mcp.tool
    async def get_goal_context() -> dict[str, Any]:
        """读取当前目标的关键信息：标题、截止日期、每周可投入小时、里程碑列表，
        以及上次提案被拒的原因（若有）——本轮排程要针对它做对应调整。"""
        # 上次被拒提案的原因（反馈闭环：拒绝 → 原因 → 本轮针对性调整）
        last_rejected = (
            await ctx.session.execute(
                select(PlanProposal.rejection_reason)
                .join(WeeklyPlan, PlanProposal.weekly_plan_id == WeeklyPlan.id)
                .where(
                    WeeklyPlan.goal_id == ctx.goal.id,
                    PlanProposal.status == ProposalStatus.REJECTED,
                    PlanProposal.rejection_reason.is_not(None),
                )
                .order_by(PlanProposal.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "title": ctx.goal.title,
            "deadline": ctx.goal.deadline.isoformat() if ctx.goal.deadline else None,
            "weekly_hours": ctx.goal.weekly_hours,
            "milestones": [
                {"title": m.title, "due_date": m.due_date.isoformat() if m.due_date else None}
                for m in ctx.goal.milestones
            ],
            "last_rejection_reason": last_rejected,
        }

    @mcp.tool
    async def get_execution_history(window_days: int = 14) -> dict[str, Any]:
        """读取近期执行历史：完成率、跳过原因分布、各时段（北京小时）完成/跳过规律，
        以及复盘师最近一期周报的洞察。

        排程前必读——让计划适应用户的真实行为（如常在晚间因疲劳跳过 →
        下调晚间任务量或调整科目），而不是每周从零重排。
        复盘师洞察（另一位 Agent 的分析结论）与统计数据互相印证，一并参考。
        """
        stats = StatsService(ctx.session)
        skip = await stats.skip_reasons(ctx.user_id, window_days)
        hours = await stats.hours(ctx.user_id, window_days)
        # 上一完整自然周（周一~周日）：本周至今只有 1-2 天数据时完成率
        # 严重噪声（做 1 件 100%/漏 1 件 0%），教练据此会错误下调计划
        this_monday = today_cn() - timedelta(days=today_cn().weekday())
        prev_monday = this_monday - timedelta(days=7)
        heatmap = await stats.heatmap(ctx.user_id, 2)
        prev_week = [
            d for d in heatmap.days if prev_monday <= d.date <= prev_monday + timedelta(days=6)
        ]
        done = sum(d.done for d in prev_week)
        total = sum(d.total for d in prev_week)
        # 复盘师 → 教练的消息通道：最近一期周报的洞察随执行数据一并下发
        last_report = (
            await ctx.session.execute(
                select(WeeklyReport.title, WeeklyReport.content)
                .where(WeeklyReport.user_id == ctx.user_id)
                .order_by(WeeklyReport.week_start.desc())
                .limit(1)
            )
        ).first()
        insight = None
        if last_report is not None:
            insight = f"{last_report.title}——{last_report.content[:300]}"

        # 时段规律提炼：完成最集中与跳过最集中的前 3 个小时（计数为 0 的剔除）
        def top_hours(hist: list[int]) -> list[int]:
            ranked = sorted(range(24), key=lambda h: -hist[h])[:3]
            return [h for h in ranked if hist[h] > 0]

        return {
            "window_days": window_days,
            "last_week": {
                "done": done,
                "total": total,
                "completion_rate": round(done / total, 2) if total else None,
            },
            "skip_reasons": [{"reason": s.reason, "count": s.count} for s in skip.items],
            "best_hours": top_hours(hours.completion_hours),
            "worst_hours": top_hours(hours.skip_hours),
            "reviewer_insight": insight,  # 复盘师（另一 Agent）对上周的结论，无周报时为 None
            "note": "best/worst_hours 为北京小时；worst 时段的任务历史上大多被跳过",
        }

    @mcp.tool
    async def schedule_week(subjects: list[dict[str, Any]], weekly_hours: float) -> dict[str, Any]:
        """运行确定性排程算法。subjects 形如
        [{"label": "下肢力量", "weekly_hours": 2.5, "items": ["深蹲 4×8", "硬拉 3×5"]}]
        （items 可选：该科目的具体动作/学习单元，排程按天轮换写进任务标题）；
        weekly_hours 为该用户每周总预算小时。返回任务清单与超载标记。"""
        allocations = [
            SubjectAllocation(
                label=str(s.get("label", "")),
                weekly_hours=float(s.get("weekly_hours", 0)),
                items=tuple(str(i) for i in s.get("items") or [] if str(i).strip()),
            )
            for s in subjects
            if s.get("label")
        ]
        result = run_scheduler(allocations, weekly_hours)
        payload: dict[str, Any] = {
            "tasks": [
                {
                    "date": t.date.isoformat(),
                    "title": t.title,
                    "duration_minutes": t.duration_minutes,
                    "category_label": t.category_label,
                }
                for t in result.tasks
            ],
            "overloaded": result.overloaded,
            "requested_minutes": result.requested_minutes,
            "capacity_minutes": result.capacity_minutes,
            "note": result.note,
        }
        ctx.last_schedule = payload
        return payload

    @mcp.tool
    async def submit_proposal(tasks: list[dict[str, Any]], summary: str) -> dict[str, Any]:
        """提交周计划草案等待人工审批（创建草稿计划与任务，用户批准后才会生效）。
        tasks 形如 [{"date": "2026-09-28", "title": "...", "duration_minutes": 45,
        "category_label": "数学"}]。"""
        if ctx.proposal_id is not None:
            return {"proposal_id": ctx.proposal_id, "plan_id": ctx.plan_id, "duplicate": True}

        # 校验先行：LLM 输出全部通过校验才允许建任何东西（不留孤儿草稿计划）
        validated, error = _validate_tasks(tasks)
        if error:
            return {"error": error}
        plan_repo = WeeklyPlanRepository(ctx.session)
        task_repo = TaskRepository(ctx.session)
        for attempt in range(2):  # 版本号唯一约束冲突时重试一次
            version = await plan_repo.next_version(ctx.goal.id, _current_week_start())
            try:
                plan = await plan_repo.create(
                    goal_id=ctx.goal.id,
                    week_start=_current_week_start(),
                    status=PlanStatus.DRAFT,
                    version=version,
                )
                for item in validated:
                    await task_repo.create(
                        weekly_plan_id=plan.id,
                        date=item["date"],
                        title=item["title"],
                        duration_minutes=item["duration_minutes"],
                        category_label=item["category_label"],
                    )
            except IntegrityError:
                # 并发导入同一目标同一周：版本号撞唯一约束，回滚重算一次
                await ctx.session.rollback()
                if attempt == 1:
                    return {"error": "计划版本冲突，请稍后重试"}
                continue
            break
        proposal = await PlanProposalRepository(ctx.session).create(
            weekly_plan_id=plan.id,
            diff={"summary": summary, "tasks": [t["iso"] for t in validated]},
            note=summary,
        )
        ctx.proposal_id = proposal.id
        ctx.plan_id = plan.id
        ctx.summary = summary
        return {
            "proposal_id": proposal.id,
            "plan_id": plan.id,
            "task_count": len(validated),
            "status": "等待用户审批",
        }

    return mcp


_MAX_TASKS_PER_PROPOSAL = 50
_MIN_DURATION = 1
_MAX_DURATION = 240


def _validate_tasks(tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """LLM 提交的任务清单 → (规范化结果, 错误)。校验不过返回错误、不产生任何写入。"""
    if not tasks:
        return [], "任务列表为空，请用 schedule_week 的结果调用本工具"
    if len(tasks) > _MAX_TASKS_PER_PROPOSAL:
        return [], f"任务数超上限（{len(tasks)} > {_MAX_TASKS_PER_PROPOSAL}），请精简后提交"
    normalized: list[dict[str, Any]] = []
    for index, t in enumerate(tasks):
        try:
            task_date = date.fromisoformat(str(t["date"]))
        except (KeyError, ValueError, TypeError):
            return [], f"第 {index + 1} 条任务日期非法: {t.get('date')!r}，需要 YYYY-MM-DD"
        raw_duration = t.get("duration_minutes", 30)
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            return [], f"第 {index + 1} 条任务时长非法: {raw_duration!r}"
        if not _MIN_DURATION <= duration <= _MAX_DURATION:
            return [], f"第 {index + 1} 条任务时长需在 {_MIN_DURATION}-{_MAX_DURATION} 分钟内"
        title = str(t.get("title") or "未命名任务").strip()[:200]
        if not title:
            title = "未命名任务"
        normalized.append(
            {
                "date": task_date,
                "title": title,
                "duration_minutes": duration,
                "category_label": str(t.get("category_label") or "")[:50],
                "iso": {
                    "date": task_date.isoformat(),
                    "title": title,
                    "duration_minutes": duration,
                    "category_label": str(t.get("category_label") or "")[:50],
                },
            }
        )
    return normalized, None


def _current_week_start() -> date:
    return next_monday(today_cn())
