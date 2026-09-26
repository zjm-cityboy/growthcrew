"""P4 错题本测试：录题/LLM 讲解/间隔复习/掌握/到期/晨推集成。"""

from app.agents.llm import AssistantResult
from app.jobs.briefs import render_morning_brief
from app.schemas.mistake import MistakeCreateIn
from app.schemas.today import DaySummaryOut, TodayOut
from app.services.mistake import MistakeService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user, _today
from tests.test_p12_agent import FakeBackend

_EXPLAIN_TEXT = (
    "正确答案是 B。你的误区在于混淆了进程和线程的内存空间——"
    "线程共享进程的地址空间，但各有自己的栈。记忆口诀：'线程共享堆，各有栈'。"
)


async def _create_mistake_with_fake(
    engine: AsyncEngine, user_id: int, backend: FakeBackend
) -> dict:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        service = MistakeService(session)
        mistake = await service.create(
            user_id,
            MistakeCreateIn(
                question="进程和线程的区别是什么？",
                wrong_answer="线程有自己的独立地址空间",
                source="操作系统期末考试",
            ),
            backend=backend,
        )
        return mistake.model_dump()


async def test_create_mistake_with_llm(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "mistake_user")
    result = await _create_mistake_with_fake(
        engine, user_id, FakeBackend([AssistantResult(content=_EXPLAIN_TEXT)])
    )
    assert "线程共享" in result["explanation"]
    assert result["review_count"] == 0
    assert result["interval_days"] == 1
    assert result["mastered"] is False
    # 明天开始复习（next_review_at 是 date，不是 str）
    from datetime import date as _date

    assert isinstance(result["next_review_at"], _date)
    assert result["next_review_at"] > _today()


async def test_create_mistake_without_byok(client: AsyncClient, engine: AsyncEngine) -> None:
    """无 BYOK 时仍保存题目，只是没有讲解。"""
    user_id = await _create_user(engine, "mistake_bare")
    resp = await client.post(
        "/api/v1/mistakes",
        json={"question": "TCP 三次握手第二步是什么？", "source": "计算机网络"},
        headers=_auth(user_id),
    )
    assert resp.status_code == 201
    assert "暂无讲解" in resp.json()["explanation"]


async def test_review_correct_doubles_interval(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "review_user")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        service = MistakeService(session)
        mistake = await service.create(
            user_id,
            MistakeCreateIn(question="进程调度算法有哪些？"),
            backend=FakeBackend([AssistantResult(content="先来先服务、短作业优先、轮转…")]),
        )
        mistake_id = mistake.id

    headers = _auth(user_id)
    # 第一次答对：1→2
    r1 = await client.post(
        f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=headers
    )
    assert r1.status_code == 200
    assert r1.json()["interval_days"] == 2
    assert r1.json()["review_count"] == 1

    # 第二次答对：2→4
    r2 = await client.post(
        f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=headers
    )
    assert r2.json()["interval_days"] == 4
    assert r2.json()["review_count"] == 2


async def test_review_wrong_resets(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "wrong_user")
    result = await _create_mistake_with_fake(
        engine, user_id, FakeBackend([AssistantResult(content="讲解")])
    )
    mistake_id = result["id"]

    # 先答对一次
    await client.post(
        f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=_auth(user_id)
    )
    # 再答错：重置
    resp = await client.post(
        f"/api/v1/mistakes/{mistake_id}/review", json={"correct": False}, headers=_auth(user_id)
    )
    assert resp.json()["interval_days"] == 1
    assert resp.json()["review_count"] == 0


async def test_mastery_after_5_consecutive(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "mastery_user")
    result = await _create_mistake_with_fake(
        engine, user_id, FakeBackend([AssistantResult(content="讲解")])
    )
    mistake_id = result["id"]
    headers = _auth(user_id)

    for _ in range(5):
        resp = await client.post(
            f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=headers
        )
    assert resp.json()["mastered"] is True
    assert resp.json()["interval_days"] == 32

    # 已掌握后再复习 → 409
    again = await client.post(
        f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=headers
    )
    assert again.status_code == 409


async def test_cross_user_mistake_invisible(client: AsyncClient, engine: AsyncEngine) -> None:
    """跨用户：B 不能看/复习 A 的错题（404 不泄露存在性）。"""
    owner = await _create_user(engine, "mistake_owner")
    intruder = await _create_user(engine, "mistake_intruder")
    result = await _create_mistake_with_fake(
        engine, owner, FakeBackend([AssistantResult(content="讲解")])
    )
    mistake_id = result["id"]

    # intruder 看不到 owner 的错题
    review = await client.post(
        f"/api/v1/mistakes/{mistake_id}/review",
        json={"correct": True},
        headers=_auth(intruder),
    )
    assert review.status_code == 404

    # intruder 的 due 列表里也没有
    due = await client.get("/api/v1/mistakes/due", headers=_auth(intruder))
    assert due.json()["due_count"] == 0
    assert len(due.json()["mistakes"]) == 0


async def test_mastered_excluded_from_due_and_brief(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """掌握后的错题不再出现在 due 列表和晨推计数里。"""
    user_id = await _create_user(engine, "excl_user")
    result = await _create_mistake_with_fake(
        engine, user_id, FakeBackend([AssistantResult(content="讲解")])
    )
    mistake_id = result["id"]
    headers = _auth(user_id)

    # 先把到期日改成今天（让它到期）
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.core.time import today_cn
        from app.models.mistake import Mistake
        from sqlalchemy import update

        await session.execute(
            update(Mistake).where(Mistake.id == mistake_id).values(next_review_at=today_cn())
        )
        await session.commit()

    # 到期时 due 有 1 道
    due = await client.get("/api/v1/mistakes/due", headers=headers)
    assert due.json()["due_count"] == 1

    # 连续答对 5 次掌握
    for _ in range(5):
        await client.post(
            f"/api/v1/mistakes/{mistake_id}/review", json={"correct": True}, headers=headers
        )

    # 掌握后 due 归零
    due_after = await client.get("/api/v1/mistakes/due", headers=headers)
    assert due_after.json()["due_count"] == 0


async def test_due_list_and_morning_brief(client: AsyncClient, engine: AsyncEngine) -> None:
    """到期列表 + 晨推集成：错题数混入晨推文案。"""
    user_id = await _create_user(engine, "due_user")
    headers = _auth(user_id)

    # 录一道（明天到期）
    await client.post(
        "/api/v1/mistakes",
        json={"question": "什么是死锁的四个必要条件？"},
        headers=headers,
    )

    # 手动把到期日改成今天（模拟明天到了）
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.core.time import today_cn
        from app.models.mistake import Mistake
        from sqlalchemy import update

        await session.execute(update(Mistake).values(next_review_at=today_cn()))
        await session.commit()

    due = await client.get("/api/v1/mistakes/due", headers=headers)
    assert due.status_code == 200
    assert due.json()["due_count"] == 1

    # 晨推集成
    today = TodayOut(
        date=_today(),
        yesterday=DaySummaryOut(done=0, total=0),
        tasks=[],
        life_log=None,
        journal_submitted=False,
        streak=0,
    )
    title, body = render_morning_brief(today, due_mistakes=1)
    assert "1 道错题" in title
    assert "错题到期" in body
