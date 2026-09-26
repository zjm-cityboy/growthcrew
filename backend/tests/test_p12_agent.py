"""教练 Agent 全链路测试（LLM 全 mock，CI 零网络零 token）。

FakeBackend 按脚本逐条返回，验证的是编排逻辑：
解析 → 读目标 → 排程（超载）→ 下调重排 → 提案 → 审批生效 → 今日可见。
"""

from datetime import timedelta
from typing import Any

from app.agents.llm import AssistantResult, ToolCall
from app.services.plan_import import PlanImportService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user, _today

_RAW_TEXT = "软考高级：9-10 月过一轮教材，11 月真题二刷，每天数学 2 小时、案例 1 小时"


class FakeBackend:
    """按脚本回放的 LLM 替身，实现 LLMBackend 协议。"""

    def __init__(self, script: list[AssistantResult]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        forced_tool: str | None = None,
    ) -> AssistantResult:
        self.calls.append({"n_messages": len(messages), "forced_tool": forced_tool})
        if not self._script:
            raise AssertionError("FakeBackend 脚本耗尽")
        return self._script.pop(0)


def _tool(call_id: str, name: str, arguments: dict[str, Any]) -> AssistantResult:
    return AssistantResult(tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])


async def _create_goal(client: AsyncClient, user_id: int, **overrides: Any) -> int:
    payload: dict[str, Any] = {
        "title": "软考高级冲刺",
        "category": "备考",
        "deadline": (_today() + timedelta(days=60)).isoformat(),
        "weekly_hours": 10,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/goals", json=payload, headers=_auth(user_id))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _import_with_fake(
    client: AsyncClient,
    engine: AsyncEngine,
    user_id: int,
    goal_id: int,
    fake: FakeBackend,
    weekly_hours: float | None = None,
) -> dict[str, Any]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.schemas.proposal import ImportPlanIn

        service = PlanImportService(session)
        outcome = await service.start(
            user_id,
            ImportPlanIn(goal_id=goal_id, raw_text=_RAW_TEXT, weekly_hours=weekly_hours),
            backend=fake,
        )
        return outcome.model_dump()


def _full_flow_script(next_monday_iso: str, today_iso: str) -> list[AssistantResult]:
    """解析 → 读目标 → 排程(超载) → 下调重排 → 提交提案。"""
    return [
        _tool(
            "c1",
            "submit_parsed_plan",
            {
                "subjects": [
                    {"label": "数学", "weekly_hours": 10},
                    {"label": "案例", "weekly_hours": 8},
                ],
                "note": "9-10 月一轮教材",
            },
        ),
        _tool("c2", "get_goal_context", {}),
        _tool(
            "c3",
            "schedule_week",
            {
                "subjects": [
                    {"label": "数学", "weekly_hours": 10},
                    {"label": "案例", "weekly_hours": 8},
                ],
                "weekly_hours": 10,
            },
        ),
        _tool(
            "c4",
            "schedule_week",
            {
                "subjects": [
                    {"label": "数学", "weekly_hours": 6},
                    {"label": "案例", "weekly_hours": 4},
                ],
                "weekly_hours": 10,
            },
        ),
        _tool(
            "c5",
            "submit_proposal",
            {
                "tasks": [
                    {
                        "date": today_iso,
                        "title": "数学 · 专注 90 分钟",
                        "duration_minutes": 90,
                        "category_label": "数学",
                    },
                    {
                        "date": next_monday_iso,
                        "title": "案例 · 专注 60 分钟",
                        "duration_minutes": 60,
                        "category_label": "案例",
                    },
                ],
                "summary": "按每周 10 小时预算排布：数学 6h + 案例 4h",
            },
        ),
    ]


def _next_monday_iso() -> str:
    from app.agents.scheduler import next_monday

    return next_monday(_today()).isoformat()


async def test_full_flow_import_approve_today(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "agent_user")
    goal_id = await _create_goal(client, user_id)
    fake = FakeBackend(_full_flow_script(_next_monday_iso(), _today().isoformat()))

    result = await _import_with_fake(client, engine, user_id, goal_id, fake)
    assert result["status"] == "proposal"
    assert result["proposal_id"] is not None
    assert "10 小时" in result["summary"]
    assert len(fake.calls) == 5  # 解析 1 次 + 教练循环 4 轮

    headers = _auth(user_id)
    detail = await client.get(f"/api/v1/proposals/{result['proposal_id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "待审批"
    assert len(body["tasks"]) == 2
    assert body["version"] == 1

    # 审批前：今日不可见（草稿计划）
    today_before = await client.get("/api/v1/today", headers=headers)
    assert today_before.json()["tasks"] == []

    approved = await client.post(
        f"/api/v1/proposals/{result['proposal_id']}/approve", headers=headers
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "已同意"

    # 审批后：今日出现该计划里日期为今天的任务
    today_after = await client.get("/api/v1/today", headers=headers)
    titles = [t["title"] for t in today_after.json()["tasks"]]
    assert titles == ["数学 · 专注 90 分钟"]

    # 通知到位
    notifications = await client.get("/api/v1/notifications", headers=headers)
    assert any(n["title"] == "新计划已生效" for n in notifications.json())

    # 重复审批 → 409
    again = await client.post(f"/api/v1/proposals/{result['proposal_id']}/approve", headers=headers)
    assert again.status_code == 409


async def test_new_version_supersedes_old(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "version_user")
    goal_id = await _create_goal(client, user_id)
    headers = _auth(user_id)

    first = await _import_with_fake(
        client,
        engine,
        user_id,
        goal_id,
        FakeBackend(_full_flow_script(_next_monday_iso(), _today().isoformat())),
    )
    await client.post(f"/api/v1/proposals/{first['proposal_id']}/approve", headers=headers)

    # 第二版提案：任务换个标题
    second_script = _full_flow_script(_next_monday_iso(), _today().isoformat())
    second_script[-1] = _tool(
        "s5",
        "submit_proposal",
        {
            "tasks": [
                {
                    "date": _today().isoformat(),
                    "title": "案例 · 专注 45 分钟",
                    "duration_minutes": 45,
                    "category_label": "案例",
                }
            ],
            "summary": "调整：案例优先",
        },
    )
    second = await _import_with_fake(client, engine, user_id, goal_id, FakeBackend(second_script))
    assert second["plan_id"] != first["plan_id"]

    approved2 = await client.post(
        f"/api/v1/proposals/{second['proposal_id']}/approve", headers=headers
    )
    assert approved2.status_code == 200

    # 今日只剩新版任务（旧计划已被替代）
    today = await client.get("/api/v1/today", headers=headers)
    titles = [t["title"] for t in today.json()["tasks"]]
    assert titles == ["案例 · 专注 45 分钟"]


async def test_reject_keeps_plan_draft(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "reject_user")
    goal_id = await _create_goal(client, user_id)
    headers = _auth(user_id)

    result = await _import_with_fake(
        client,
        engine,
        user_id,
        goal_id,
        FakeBackend(_full_flow_script(_next_monday_iso(), _today().isoformat())),
    )
    rejected = await client.post(
        f"/api/v1/proposals/{result['proposal_id']}/reject", headers=headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "已拒绝"

    # 拒绝后：今日仍为空；再想批准 → 409
    today = await client.get("/api/v1/today", headers=headers)
    assert today.json()["tasks"] == []
    approve_after = await client.post(
        f"/api/v1/proposals/{result['proposal_id']}/approve", headers=headers
    )
    assert approve_after.status_code == 409


async def test_missing_info_returns_questions(client: AsyncClient, engine: AsyncEngine) -> None:
    """缺截止日期与每周时长：返回追问而不是硬编计划。"""
    user_id = await _create_user(engine, "question_user")
    goal_id = await _create_goal(client, user_id, deadline=None, weekly_hours=None)
    fake = FakeBackend([])  # 不应触达 LLM
    result = await _import_with_fake(client, engine, user_id, goal_id, fake)
    assert result["status"] == "questions"
    assert len(result["questions"]) == 2
    assert fake.calls == []


async def test_import_without_byok_returns_400(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "nobyyok_user")
    goal_id = await _create_goal(client, user_id)
    resp = await client.post(
        "/api/v1/plans/import",
        json={"goal_id": goal_id, "raw_text": _RAW_TEXT},
        headers=_auth(user_id),
    )
    assert resp.status_code == 400
    assert "BYOK" in resp.json()["detail"]


async def test_invalid_tasks_retry_leaves_no_orphan_plan(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """LLM 先交非法任务 → 工具拒绝且不产生任何写入 → 修正后成功，计划表只有一份。"""
    user_id = await _create_user(engine, "orphan_user")
    goal_id = await _create_goal(client, user_id)

    good_tasks = [
        {
            "date": _today().isoformat(),
            "title": "数学 · 专注 60 分钟",
            "duration_minutes": 60,
            "category_label": "数学",
        }
    ]
    script = [
        _full_flow_script(_next_monday_iso(), _today().isoformat())[0],  # parse
        _tool(
            "x1",
            "submit_proposal",
            {
                "tasks": [{"date": "不是日期", "title": "坏任务", "duration_minutes": 60}],
                "summary": "坏提案",
            },
        ),
        _tool("x2", "submit_proposal", {"tasks": good_tasks, "summary": "修正后的提案"}),
    ]
    result = await _import_with_fake(client, engine, user_id, goal_id, FakeBackend(script))
    assert result["status"] == "proposal"

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.models.plan import WeeklyPlan
        from sqlalchemy import func, select

        count = await session.scalar(
            select(func.count()).select_from(WeeklyPlan).where(WeeklyPlan.goal_id == goal_id)
        )
    assert count == 1  # 校验先行的回归断言：失败尝试不留孤儿草稿


async def test_task_limit_and_duration_rejected(client: AsyncClient, engine: AsyncEngine) -> None:
    """超 50 条与时长越界都会被工具拒绝并回喂错误，修正后可成功。"""
    user_id = await _create_user(engine, "limit_user")
    goal_id = await _create_goal(client, user_id)

    too_many = [
        {"date": _today().isoformat(), "title": f"任务{i}", "duration_minutes": 30}
        for i in range(51)
    ]
    bad_duration = [{"date": _today().isoformat(), "title": "超长任务", "duration_minutes": 99999}]
    good = [{"date": _today().isoformat(), "title": "正常任务", "duration_minutes": 45}]
    parse = _full_flow_script(_next_monday_iso(), _today().isoformat())[0]
    script = [
        parse,
        _tool("y1", "submit_proposal", {"tasks": too_many, "summary": "超量"}),
        _tool("y2", "submit_proposal", {"tasks": bad_duration, "summary": "越界"}),
        _tool("y3", "submit_proposal", {"tasks": good, "summary": "合格"}),
    ]
    result = await _import_with_fake(client, engine, user_id, goal_id, FakeBackend(script))
    assert result["status"] == "proposal"


async def test_parse_without_tool_calls_fails_gracefully(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """模型忽略 forced_tool 返回纯文本：应得业务错误而非 IndexError 500。"""
    import pytest
    from app.schemas.proposal import ImportPlanIn
    from app.services.errors import PlannerFailedError
    from app.services.plan_import import PlanImportService

    user_id = await _create_user(engine, "stray_user")
    goal_id = await _create_goal(client, user_id)
    fake = FakeBackend([AssistantResult(content="这段文本我看不懂")])

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        service = PlanImportService(session)
        with pytest.raises(PlannerFailedError):
            await service.start(
                user_id,
                ImportPlanIn(goal_id=goal_id, raw_text=_RAW_TEXT),
                backend=fake,
            )
