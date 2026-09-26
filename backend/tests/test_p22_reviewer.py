"""P2.2 复盘师测试：周报工具循环 / 周三小结 / 定时任务去重与隔离（FakeBackend 全 mock）。"""

from app.agents.llm import AssistantResult, ToolCall
from app.domain.enums import NotificationType, TaskStatus
from app.jobs.reports import midweek_brief_job, weekly_report_job
from app.repositories.notification import NotificationRepository
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user, _seed_plan_tasks, _today
from tests.test_p12_agent import FakeBackend


def _tool(call_id: str, name: str, arguments: dict) -> AssistantResult:
    return AssistantResult(tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])


def _weekly_script() -> list[AssistantResult]:
    """拿统计 → 钻卡因 → 钻时段 → 提交周报（复盘师的典型路径）。"""
    return [
        _tool("r1", "get_week_stats", {}),
        _tool("r2", "get_skip_reasons", {}),
        _tool("r3", "get_hour_patterns", {}),
        _tool(
            "r4",
            "submit_report",
            {
                "title": "稳中有升的一周",
                "content": (
                    "本周完成 6/8（75%），连续打卡 5 天。"
                    "卡因显示『疲劳』占跳过的一半，且集中在 22 点后的时段——"
                    "你的深夜任务实际都在被疲劳吞掉。"
                    "建议：把政治背诵挪到下午，晚间只留轻量复盘。"
                ),
            },
        ),
    ]


async def _seed_week(engine: AsyncEngine, user_id: int) -> None:
    from datetime import timedelta

    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today() - timedelta(days=1), "A", TaskStatus.DONE),
            (_today() - timedelta(days=1), "B", TaskStatus.DONE),
            (_today(), "C", TaskStatus.TODO),
        ],
    )


async def test_weekly_report_full_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "review_user")
    headers = _auth(user_id)
    await _seed_week(engine, user_id)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.services.review import ReviewService

        service = ReviewService(session)
        report = await service.generate_weekly(user_id, backend=FakeBackend(_weekly_script()))
        report_id = report.id
        title = report.title

    assert "稳中有升" in title

    detail = await client.get(f"/api/v1/reports/weekly/{report_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert "疲劳" in body["content"]
    assert "week_stats" in body["data_snapshot"]  # 统计快照随报告存档
    assert "skip_reasons" in body["data_snapshot"]

    listed = await client.get("/api/v1/reports/weekly", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # 周报通知已发
    async with maker() as session:
        notifications = await NotificationRepository(session).list_for_user(user_id)
    assert any(n.type == NotificationType.WEEKLY_REPORT for n in notifications)


async def test_weekly_report_job_dedup_and_skip(client: AsyncClient, engine: AsyncEngine) -> None:
    """定时任务：已有本周周报（手动生成过）→ 跳过；未配置 BYOK → 跳过。"""
    configured = await _create_user(engine, "review_cfg")
    await _create_user(engine, "review_bare")  # 无 BYOK 用户：任务应静默跳过
    await _seed_week(engine, configured)

    maker = async_sessionmaker(engine, expire_on_commit=False)

    # bare 用户无 BYOK：跳过且不算失败
    first = await weekly_report_job(maker)
    assert first == 0  # 两个都跳过（一个无 BYOK、一个也无）

    # 给 configured 配 BYOK（服务层直写，不加密测试可接受：走真实 save 流程）
    from app.schemas.settings import LLMSettingsIn
    from app.services.llm_settings import LLMSettingsService

    async with maker() as session:
        await LLMSettingsService(session).save(
            configured,
            LLMSettingsIn(
                base_url="https://api.siliconflow.cn/v1",
                api_key="sk-test-12345678",
                model_name="test-model",
            ),
        )

    # BYOK 已配但 LLM 后端在任务里会被真实调用——这里只验证"已有周报跳过"分支：
    # 先手动生成一份，再跑任务 → skipped
    async with maker() as session:
        from app.services.review import ReviewService

        await ReviewService(session).generate_weekly(
            configured, backend=FakeBackend(_weekly_script())
        )

    second = await weekly_report_job(maker)
    assert second == 0  # configured 本周已有 → 跳过；bare 无 BYOK → 跳过


async def test_submit_report_validation_branches(client: AsyncClient, engine: AsyncEngine) -> None:
    """submit_report 三条校验分支：跳过取数 / 正文过短 / 修正后成功。"""
    user_id = await _create_user(engine, "valid_user")
    await _seed_week(engine, user_id)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    long_enough = "本周完成 2/3，卡因集中在深夜疲劳时段，建议政治挪下午。" * 2

    script = [
        # ① 不取数直接提交 → 被拒（缺 week_stats 快照）
        _tool("v0", "submit_report", {"title": "无数据周报", "content": long_enough}),
        # ② 取数后交短正文 → 被拒
        _tool("v1", "get_week_stats", {}),
        _tool("v2", "submit_report", {"title": "太短", "content": "只有一句话"}),
        # ③ 修正后成功
        _tool("v3", "submit_report", {"title": "合格周报", "content": long_enough}),
    ]
    async with maker() as session:
        from app.services.review import ReviewService

        report = await ReviewService(session).generate_weekly(user_id, backend=FakeBackend(script))
    assert report.title == "合格周报"
    assert report.data_snapshot["week_stats"]["done"] >= 1  # 快照取自真实种子数据


async def test_weekly_upsert_overwrites_same_week(client: AsyncClient, engine: AsyncEngine) -> None:
    """同周重跑覆盖（upsert 更新路径）。"""
    user_id = await _create_user(engine, "upsert_user")
    await _seed_week(engine, user_id)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    content_a = "第一版周报：" + "完成情况稳中有升，疲劳卡因值得注意。" * 3
    content_b = "第二版周报：" + "数据补充后更新了洞察，政治建议挪到下午。" * 3
    async with maker() as session:
        from app.services.review import ReviewService

        first = await ReviewService(session).generate_weekly(
            user_id,
            backend=FakeBackend(
                [
                    _tool("a1", "get_week_stats", {}),
                    _tool("a2", "submit_report", {"title": "第一版", "content": content_a}),
                ]
            ),
        )
        second = await ReviewService(session).generate_weekly(
            user_id,
            backend=FakeBackend(
                [
                    _tool("b1", "get_week_stats", {}),
                    _tool("b2", "submit_report", {"title": "第二版", "content": content_b}),
                ]
            ),
        )

    assert first.id == second.id  # 同一条记录被覆盖，不是新增
    assert second.title == "第二版"

    from app.repositories.report import WeeklyReportRepository

    async with maker() as session:
        listed = await WeeklyReportRepository(session).list_for_user(user_id)
    assert len(listed) == 1


async def test_midweek_brief_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "midweek_user")
    await _seed_week(engine, user_id)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from app.services.review import ReviewService

        service = ReviewService(session)
        content = await service.generate_midweek(
            user_id,
            backend=FakeBackend(
                [AssistantResult(content="半程完成 2/3，下午把政治挪前一点就好。")]
            ),
        )

    assert "政治" in content

    async with maker() as session:
        notifications = await NotificationRepository(session).list_for_user(user_id)
    assert any(
        n.type == NotificationType.MIDWEEK_BRIEF and "政治" in (n.body or "") for n in notifications
    )

    # 任务级当日去重：已有 MIDWEEK_BRIEF 通知 → 跳过
    created = await midweek_brief_job(maker)
    assert created == 0  # 无 BYOK 用户 + 已发过 → 均跳过


async def test_reports_without_byok_returns_400(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "nobyyok_review")
    resp = await client.post("/api/v1/reports/weekly", headers=_auth(user_id))
    assert resp.status_code == 400
    assert "BYOK" in resp.json()["detail"]


async def test_scheduler_registers_four_jobs() -> None:
    from app.core.config import get_settings
    from app.jobs.scheduler import build_scheduler

    scheduler = build_scheduler(async_sessionmaker(), get_settings())
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"morning_brief", "evening_reminder", "weekly_report", "midweek_brief"}
