"""P3 数据导出测试：CSV 格式 / 数据完整性 / 公式注入防护 / 鉴权。"""

from app.domain.enums import TaskStatus
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.test_p1_core import _auth, _create_user, _seed_plan_tasks, _today


async def test_export_csv_full_data(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "export_user")
    headers = _auth(user_id)
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today(), "数学 · 专注 90 分钟", TaskStatus.DONE),
            (_today(), "英语阅读", TaskStatus.SKIPPED),
        ],
    )
    await client.post(
        "/api/v1/life-logs", json={"sleep_hours": 7.0, "exercise": True}, headers=headers
    )
    await client.post(
        "/api/v1/journals/today", json={"mood": 4, "note": "状态不错"}, headers=headers
    )

    resp = await client.get("/api/v1/export/csv", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")

    text = resp.text
    assert "## 目标 ##" in text
    assert "## 里程碑 ##" in text
    assert "## 任务" in text
    assert "## 生活三打卡 ##" in text
    assert "## 晚间复盘 ##" in text
    assert "## 成长周报 ##" in text
    assert "## 通知历史 ##" in text
    assert "秋招冲刺" in text
    assert "数学" in text
    assert "7.0" in text
    assert "状态不错" in text


async def test_export_csv_formula_injection_guard(client: AsyncClient, engine: AsyncEngine) -> None:
    """以 = 开头的文本必须加 ' 前缀（OWASP CSV 注入防护）。"""
    user_id = await _create_user(engine, "inject_user")
    await client.post(
        "/api/v1/goals",
        json={"title": "=SUM(A1:A10)", "category": "备考"},
        headers=_auth(user_id),
    )
    resp = await client.get("/api/v1/export/csv", headers=_auth(user_id))
    assert resp.status_code == 200
    assert "'=SUM" in resp.text  # 被加了 ' 前缀
    for line in resp.text.split("\n"):
        if "SUM" in line:
            assert "'=SUM" in line, f"公式注入防护失败: {line}"


async def test_export_csv_has_bom(client: AsyncClient, engine: AsyncEngine) -> None:
    """UTF-8 BOM：Windows Excel 中文兼容。"""
    user_id = await _create_user(engine, "bom_user")
    resp = await client.get("/api/v1/export/csv", headers=_auth(user_id))
    assert resp.status_code == 200
    assert resp.text.startswith("\ufeff")


async def test_export_csv_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/export/csv")
    assert resp.status_code == 401


async def test_export_csv_empty_user(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "export_empty")
    resp = await client.get("/api/v1/export/csv", headers=_auth(user_id))
    assert resp.status_code == 200
    assert "## 目标 ##" in resp.text
