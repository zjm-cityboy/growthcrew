"""教练 Agent：计划导入对齐（LangGraph 编排 + FastMCP 工具循环）。

流程（全部在一次 HTTP 请求内完成，ADR-0003）：
  gather_context（缺信息 → 返回追问，结束）
  → parse（强制结构化输出：科目与周时长）
  → coach（工具循环：读目标 → 排程 → 超载则下调重排 → 提交提案）
  → END（提案等待用户在服务层审批，持久化于 plan_proposals 表）

Agent 性来源：coach 节点里"下一步调哪个工具、超载了怎么办"由模型
根据上一步结果临场决定，路径不写死；排程本身是确定性算法。
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastmcp import Client
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.agents.llm import AssistantResult, LLMBackend
from app.agents.tools import PlannerContext, build_planner_tools
from app.core.time import today_cn
from app.domain.enums import TaskStatus
from app.models.goal import Goal
from app.models.plan import Task, WeeklyPlan

_MAX_TOOL_ROUNDS = 6

logger = logging.getLogger(__name__)

# 过程事件接收器：编排各阶段调用（同一事件循环内同步执行，零额外开销）。
# 事件格式 {"type": "phase|round|tool|proposal|questions", ...}，由 SSE 端点包装下发。
ProgressReporter = Callable[[dict[str, Any]], None]


def _noop(event: dict[str, Any]) -> None:
    """默认接收器：丢弃事件（非流式调用方无需关心过程）。"""


_COACH_SYSTEM_PROMPT = (
    "你是 GrowthCrew 的教练 Agent，负责根据用户的输入生成可执行的周计划。"
    "用户可能贴入两种输入："
    "A) 详细的参考计划/经验帖/课表——对齐科目与时长后排程；"
    "B) 简短的目标描述（如'我要3个月拿下软考'）——根据你的知识规划合理的科目与时长。"
    "规则：1) 先调用 get_goal_context 与 get_execution_history——"
    "get_goal_context 里的 last_rejection_reason 是用户上次拒绝提案的原因，"
    "本轮计划必须针对它做对应调整（'排得太满'→下调总量；'时段不合适'→换时段；"
    "'科目不合适'→换科目）并在说明里明确回应；"
    "get_execution_history 是你对这个用户的了解（上周完成率、跳过原因、高效/低效时段，"
    "以及复盘师 Agent 最近一期周报的洞察 reviewer_insight）——"
    "排程必须据此自适应：常跳过的时段少排、因疲劳跳过多则下调总量、"
    "高效时段安排最难科目，复盘师指出的模式要在本轮计划里正面回应，"
    "并在说明里讲清楚依据（这是计划个性化的来源）；"
    "2) 用解析出的科目与时长调用 schedule_week 排程"
    "（科目里的 items 具体动作清单必须原样传入，任务标题会带上当天做什么）；"
    "3) 若返回 overloaded=true，主动下调各科目时长（保持优先级比例）后重新排程；"
    "4) 若返回有分钟数未能排入（truncated），说明科目太碎——把小科目并入相近大科目后重排，"
    "而不是留下'部分科目未排出'的残缺计划；"
    "5) 排程不再超载后，把最终结果的**全部任务**（不是挑几件代表）"
    "调用 submit_proposal 提交审批——每天 2-3 件是正常形态，"
    "砍任务会让用户的每日打卡变空；"
    "提案摘要要完整说明本周每天做什么，不用省略号。"
    "每轮调用工具前，先用一两句中文说明你的判断与打算"
    "（如'预算 8 小时，科目总需求 10 小时，我先按比例下调再排'）——"
    "这些说明会实时展示给用户，是透明度的一部分。"
    "语言使用简体中文；不编造数据；不要输出与工具调用无关的闲聊。"
)

_PARSE_TOOL_NAME = "submit_parsed_plan"
_PARSE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": _PARSE_TOOL_NAME,
        "description": (
            "从用户输入中提取科目/主题与每周投入小时数。"
            "用户可能贴详细计划（提取实际科目）或简短目标（你根据知识规划合理科目）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subjects": {
                    "type": "array",
                    "description": (
                        "科目列表（2-6 个，覆盖目标的完整关键维度：主项+支撑项，"
                        "如减脂=训练+有氧+饮食+睡眠）。每个科目是一周内可独立安排的"
                        "训练/学习单元：按模块拆分，不合并成大类。"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": (
                                    "科目名：2-8 个字的名词短语，具体到可执行单元，"
                                    "禁止带括号补充说明（说明写进 note）。"
                                    "好：'上肢力量'/'下肢力量'/'高数-线代'/'英语听力'；"
                                    "坏：'力量训练（4练中的3次全身/分化）'"
                                ),
                            },
                            "weekly_hours": {
                                "type": "number",
                                "description": (
                                    "建议每周小时数（≥1；仅无独立时长的杂项才并入 note）"
                                ),
                            },
                            "items": {
                                "type": "array",
                                "description": (
                                    "该科目的具体动作/学习单元清单（3-7 条，来自参考计划原文"
                                    "或你的专业知识，任何领域都给：健身是动作与组数、"
                                    "备考是章节与题量、项目是任务卡、习惯是量化动作）。"
                                    "每条是一个当天可直接照做的单元，如"
                                    "'深蹲 4×8'/'听力精听 1 篇 Conversation'/"
                                    "'线代：特征值大题 20 道'/'LeetCode 数组 3 道'/"
                                    "'背单词 100 个'。排程按天轮换，"
                                    "让'练什么/学什么/做什么'落实到任务标题上"
                                ),
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["label", "weekly_hours"],
                    },
                },
                "deadline": {
                    "type": "string",
                    "description": (
                        "从文本推导的截止日期，ISO 格式 YYYY-MM-DD。"
                        "相对表述（如'3个月'）以今天为基准换算；文本无时间信息则不填。"
                    ),
                },
                "note": {"type": "string", "description": "文本中值得注意的信息"},
            },
            "required": ["subjects"],
        },
    },
}


class PlannerError(Exception):
    """模型未能产出有效结果。"""


@dataclass
class ImportOutcome:
    questions: list[str] = field(default_factory=list)
    proposal_id: int | None = None
    plan_id: int | None = None
    summary: str = ""
    parsed_deadline: date | None = None  # 从文本推导的截止日期（目标未填时回填）


def _coerce_deadline(raw: Any) -> date | None:
    """模型返回的 deadline → date（非法/缺失/**过去**返回 None）。

    模型不知道今天是几号，相对表述（"3个月"）可能幻觉出过去的日期
    （实测推出过 2024 年），必须按"输出过校验"原则丢弃。
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    return parsed if parsed > today_cn() else None


def _tool_detail(name: str, data: Any) -> str:
    """工具结果 → 给用户看的业务摘要（时间线上替代函数名的'干了什么'）。"""
    if not isinstance(data, dict) or "error" in data:
        return ""
    if name == "get_goal_context":
        title = str(data.get("goal_title") or data.get("title") or "")
        rejection = data.get("last_rejection_reason")
        base = f"读取目标「{title}」的详情" if title else "读取目标详情"
        return f"{base}（上次拒绝原因：{rejection}）" if rejection else base
    if name == "schedule_week":
        tasks = data.get("tasks")
        overloaded = bool(data.get("overloaded"))
        if isinstance(tasks, list):
            suffix = "，请求超载已按比例缩减" if overloaded else "，预算内"
            return f"排出 {len(tasks)} 件任务{suffix}"
        return "排程完成"
    if name == "submit_proposal":
        pid = data.get("proposal_id") or data.get("id")
        return f"提案 #{pid} 已提交，等你审批" if pid else "提案已提交"
    if name == "get_hour_patterns":
        return "读取历史高效时段数据"
    if name == "get_execution_history":
        last = data.get("last_week") or {}
        rate = last.get("completion_rate")
        rate_text = (
            f"上周完成率 {int(rate * 100)}%" if isinstance(rate, (int, float)) else "暂无上周数据"
        )
        worst = data.get("worst_hours") or []
        worst_text = f"，常跳过时段 {worst} 点" if worst else ""
        return f"读取执行历史：{rate_text}{worst_text}"
    return ""


class PlannerState(TypedDict, total=False):
    missing: list[str]
    parsed_subjects: list[dict[str, Any]]
    parse_note: str


class PlannerAgent:
    def __init__(
        self,
        session: AsyncSession,
        backend: LLMBackend,
        goal: Goal,
        on_event: ProgressReporter | None = None,
    ) -> None:
        self._session = session
        self._backend = backend
        self._goal = goal
        self._ctx = PlannerContext(session=session, user_id=goal.user_id, goal=goal)
        self._questions: list[str] = []
        self._parsed_deadline: date | None = None  # parse 节点从文本推导的截止日期
        self._recent_subjects: list[dict[str, Any]] = []  # 近 14 天执行过的科目（解析兜底上下文）
        self._emit: ProgressReporter = on_event or _noop

    async def run(self, raw_text: str, weekly_hours: float | None) -> ImportOutcome:
        # 近期执行过的科目（用户级，跨目标）："保持节奏/继续上周"类输入的解析兜底
        rows = await self._session.execute(
            select(Task.category_label, func.sum(Task.duration_minutes))
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Goal.user_id == self._goal.user_id,
                Task.status == TaskStatus.DONE,
                Task.date >= today_cn() - timedelta(days=14),
            )
            .group_by(Task.category_label)
        )
        self._recent_subjects = [
            # 窗口 14 天 = 2 周：折回"每周"口径，否则数字翻倍会锚死模型的建议值
            {"label": label, "weekly_hours": round(int(minutes) / 60 / 2, 1)}
            for label, minutes in rows.all()
        ]
        graph = self._build_graph(raw_text, weekly_hours)
        await graph.ainvoke({})
        ctx = self._ctx
        if ctx.proposal_id is None:
            return ImportOutcome(questions=getattr(self, "_questions", []))
        return ImportOutcome(
            proposal_id=ctx.proposal_id,
            plan_id=ctx.plan_id,
            summary=ctx.summary,
            parsed_deadline=self._parsed_deadline,
        )

    # ---------- 图构建 ----------

    def _build_graph(self, raw_text: str, weekly_hours_hint: float | None) -> Any:
        def gather(state: PlannerState) -> dict[str, Any]:
            questions: list[str] = []
            # 截止日期不追问：一句话里的时间信息（"3个月""12月考试"）
            # 由 parse 节点推导并回填目标（用户手选是可选的加速项，不是必经项）
            if not weekly_hours_hint and not self._goal.weekly_hours:
                questions.append("你每周实际能投入多少小时？（诚实估计，宁可少勿多）")
            self._questions = questions
            if questions:
                self._emit({"type": "questions", "questions": questions, "role": "coach"})
            self._emit({"type": "phase", "name": "gather", "state": "done", "role": "coach"})
            return {"missing": questions}

        async def parse(state: PlannerState) -> dict[str, Any]:
            self._emit({"type": "phase", "name": "parse", "state": "start", "role": "coach"})
            result = await self._parse_raw_text(raw_text)
            if not result.tool_calls:
                # 并非所有 OpenAI 兼容供应商都遵守 tool_choice 强制调用
                raise PlannerError("模型未按要求返回解析结果，请稍后重试")
            subjects = result.tool_calls[0].arguments.get("subjects") or []
            if not subjects:
                raise PlannerError("未能从文本中解析出科目，请检查贴入的是否为学习/训练计划")
            self._ctx.parsed_subjects = list(subjects)
            self._parsed_deadline = _coerce_deadline(result.tool_calls[0].arguments.get("deadline"))
            self._emit(
                {
                    "type": "phase",
                    "name": "parse",
                    "state": "done",
                    "subjects": len(subjects),
                    "role": "coach",
                }
            )
            return {
                "parsed_subjects": self._ctx.parsed_subjects,
                "parse_note": str(result.tool_calls[0].arguments.get("note", "")),
            }

        async def coach(state: PlannerState) -> dict[str, Any]:
            await self._coach_loop(raw_text, weekly_hours_hint, state)
            return {}

        def has_questions(state: PlannerState) -> str:
            return "questions" if state.get("missing") else "parse"

        graph = StateGraph(PlannerState)
        graph.add_node("gather", gather)
        graph.add_node("parse", parse)
        graph.add_node("coach", coach)
        graph.add_conditional_edges("gather", has_questions, {"questions": END, "parse": "parse"})
        graph.add_edge(START, "gather")
        graph.add_edge("parse", "coach")
        graph.add_edge("coach", END)
        return graph.compile()

    # ---------- 节点实现 ----------

    async def _parse_raw_text(self, raw_text: str) -> AssistantResult:
        # 注入今天日期：模型不知道"现在"是几号，没有基准"3个月"必然幻觉
        messages = [
            {
                "role": "system",
                "content": (
                    "你是计划解析器。提取科目/主题与每周建议投入小时数。"
                    f"今天是 {today_cn().isoformat()}，"
                    "文本中的相对时间（如'3个月'）以它为基准换算成 deadline。"
                    "用户可能贴详细计划（提取实际科目）或简短目标描述"
                    "（你根据知识规划合理科目，如'软考'→综合知识/案例分析/论文）。"
                    "科目名必须简短可执行（2-8 字名词短语，不带括号说明），"
                    "按模块拆分不同科目（健身按部位：上肢力量/下肢力量/核心；"
                    "备考按模块：高数-线代/英语听力；项目按工作流：需求分析/编码实现）。"
                    "不要合并成'XX训练（某某方案）'式大类。"
                    "科目要覆盖该目标的完整关键维度，不只盯着显性主项："
                    "健身减脂=力量+有氧+饮食管理+睡眠恢复；"
                    "备考=知识学习+刷题+模考复盘；学技能=教程+实战+复盘——"
                    "用户没提的维度你也要按领域知识补上（这是你的价值），"
                    "每个维度每周 1-2 小时即可单列，items 给出具体做法"
                    "（如'备次日午餐''睡前拉伸 15 分钟'）。"
                    "只有确实无独立时长的杂项（如'多喝水'）才并入 note。"
                    "每个科目 weekly_hours ≥ 1。"
                    "'保持节奏/继续上周'这类没有具体科目的输入，"
                    "用下面提供的历史科目作答，不要返回空科目。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{raw_text[:8000]}\n\n"
                    "（近 14 天实际执行过的科目供参考："
                    f"{json.dumps(self._recent_subjects, ensure_ascii=False)}）"
                ),
            },
        ]
        return await self._backend.complete(
            messages, [_PARSE_TOOL_SCHEMA], forced_tool=_PARSE_TOOL_NAME
        )

    async def _coach_loop(
        self, raw_text: str, weekly_hours_hint: float | None, state: PlannerState
    ) -> None:
        mcp = build_planner_tools(self._ctx)
        subjects = state.get("parsed_subjects", [])
        effective_hours = weekly_hours_hint or self._goal.weekly_hours
        # 截止日期：手选优先，没选则用从文本推导的（"3个月"→今天+3个月）
        effective_deadline = self._goal.deadline or self._parsed_deadline
        deadline_text = effective_deadline.isoformat() if effective_deadline else "未设置"
        user_content = (
            f"目标：{self._goal.title}"
            f"（截止 {deadline_text}）\n"
            f"每周可投入预算：{effective_hours} 小时（排程时的 weekly_hours 参数必须用它）\n"
            f"解析出的科目：{json.dumps(subjects, ensure_ascii=False)}\n"
            f"参考计划原文：\n{raw_text[:4000]}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _COACH_SYSTEM_PROMPT},
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
            for round_index in range(_MAX_TOOL_ROUNDS):
                self._emit(
                    {
                        "type": "round",
                        "index": round_index + 1,
                        "max": _MAX_TOOL_ROUNDS,
                        "role": "coach",
                    }
                )
                result = await self._backend.complete(messages, tools)
                # 教练本轮的判断说明（提示词要求输出）：实时展示给用户
                if result.content and result.content.strip():
                    self._emit(
                        {"type": "thought", "text": result.content.strip()[:160], "role": "coach"}
                    )
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
                    self._emit(
                        {"type": "tool", "name": call.name, "state": "start", "role": "coach"}
                    )
                    try:
                        tool_result = await client.call_tool(call.name, call.arguments)
                        data: Any = getattr(tool_result, "data", None)
                        if data is None:
                            data = {"error": "工具无结构化返回"}
                    except Exception:
                        # 真实异常记日志便于排查（喂给模型的提示保持简短）
                        logger.exception("工具 %s 执行失败", call.name)
                        data = {"error": "工具执行失败，请检查参数后重试"}
                    failed = isinstance(data, dict) and "error" in data
                    self._emit(
                        {
                            "type": "tool",
                            "name": call.name,
                            "state": "error" if failed else "done",
                            "detail": _tool_detail(call.name, data),
                            "role": "coach",
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(data, ensure_ascii=False),
                        }
                    )
                if self._ctx.proposal_id is not None:
                    self._emit({"type": "proposal", "id": self._ctx.proposal_id, "role": "coach"})
                    break
        if self._ctx.proposal_id is None:
            raise PlannerError("教练未能在限定轮次内产出提案")
