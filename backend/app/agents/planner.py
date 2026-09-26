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
from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.agents.llm import AssistantResult, LLMBackend
from app.agents.tools import PlannerContext, build_planner_tools
from app.models.goal import Goal

_MAX_TOOL_ROUNDS = 6

logger = logging.getLogger(__name__)

_COACH_SYSTEM_PROMPT = (
    "你是 GrowthCrew 的教练 Agent，负责根据用户的输入生成可执行的周计划。"
    "用户可能贴入两种输入："
    "A) 详细的参考计划/经验帖/课表——对齐科目与时长后排程；"
    "B) 简短的目标描述（如'我要3个月拿下软考'）——根据你的知识规划合理的科目与时长。"
    "规则：1) 先调用 get_goal_context 了解目标；"
    "2) 用解析出的科目与时长调用 schedule_week 排程；"
    "3) 若返回 overloaded=true，主动下调各科目时长（保持优先级比例）后重新排程；"
    "4) 排程不再超载后，从最终结果中挑出任务调用 submit_proposal 提交审批。"
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
                    "description": "科目列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "科目名，如 数学/专业课"},
                            "weekly_hours": {"type": "number", "description": "建议每周小时数"},
                        },
                        "required": ["label", "weekly_hours"],
                    },
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


class PlannerState(TypedDict, total=False):
    missing: list[str]
    parsed_subjects: list[dict[str, Any]]
    parse_note: str


class PlannerAgent:
    def __init__(self, session: AsyncSession, backend: LLMBackend, goal: Goal) -> None:
        self._session = session
        self._backend = backend
        self._goal = goal
        self._ctx = PlannerContext(session=session, user_id=goal.user_id, goal=goal)
        self._questions: list[str] = []

    async def run(self, raw_text: str, weekly_hours: float | None) -> ImportOutcome:
        graph = self._build_graph(raw_text, weekly_hours)
        await graph.ainvoke({})
        ctx = self._ctx
        if ctx.proposal_id is None:
            return ImportOutcome(questions=getattr(self, "_questions", []))
        return ImportOutcome(
            proposal_id=ctx.proposal_id,
            plan_id=ctx.plan_id,
            summary=ctx.summary,
        )

    # ---------- 图构建 ----------

    def _build_graph(self, raw_text: str, weekly_hours_hint: float | None) -> Any:
        def gather(state: PlannerState) -> dict[str, Any]:
            questions: list[str] = []
            if self._goal.deadline is None:
                questions.append("这个目标的截止日期是什么？（请先在目标中设置截止日期）")
            if not weekly_hours_hint and not self._goal.weekly_hours:
                questions.append("你每周实际能投入多少小时？（诚实估计，宁可少勿多）")
            self._questions = questions
            return {"missing": questions}

        async def parse(state: PlannerState) -> dict[str, Any]:
            result = await self._parse_raw_text(raw_text)
            if not result.tool_calls:
                # 并非所有 OpenAI 兼容供应商都遵守 tool_choice 强制调用
                raise PlannerError("模型未按要求返回解析结果，请稍后重试")
            subjects = result.tool_calls[0].arguments.get("subjects") or []
            if not subjects:
                raise PlannerError("未能从文本中解析出科目，请检查贴入的是否为学习/训练计划")
            self._ctx.parsed_subjects = list(subjects)
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
        messages = [
            {
                "role": "system",
                "content": (
                    "你是计划解析器。提取科目/主题与每周建议投入小时数。"
                    "用户可能贴详细计划（提取实际科目）或简短目标描述"
                    "（你根据知识规划合理科目，如'软考'→综合知识/案例分析/论文）。"
                ),
            },
            {"role": "user", "content": raw_text[:8000]},
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
        user_content = (
            f"目标：{self._goal.title}"
            f"（截止 {self._goal.deadline.isoformat() if self._goal.deadline else '未设置'}）\n"
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
            for _ in range(_MAX_TOOL_ROUNDS):
                result = await self._backend.complete(messages, tools)
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
                        # 真实异常记日志便于排查（喂给模型的提示保持简短）
                        logger.exception("工具 %s 执行失败", call.name)
                        data = {"error": "工具执行失败，请检查参数后重试"}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(data, ensure_ascii=False),
                        }
                    )
                if self._ctx.proposal_id is not None:
                    break
        if self._ctx.proposal_id is None:
            raise PlannerError("教练未能在限定轮次内产出提案")
