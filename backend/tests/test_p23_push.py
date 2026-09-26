"""P2.3 推送通道测试：配置 API / 适配器（mock httpx）/ notify_and_push 一体化。"""

from unittest.mock import AsyncMock, patch

from app.domain.enums import NotificationType
from app.repositories.notification import NotificationRepository
from app.repositories.push import PushSettingsRepository
from app.services.push import notify_and_push, validate_push_config
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user

# ---------- 配置 API ----------


async def test_push_settings_api_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "push_user")
    headers = _auth(user_id)

    # 保存 Bark 配置
    saved = await client.put(
        "/api/v1/settings/push",
        json={"channel": "bark", "endpoint": "https://api.day.app/abc123def", "enabled": True},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["channel"] == "bark"

    # 读回
    read = await client.get("/api/v1/settings/push", headers=headers)
    assert read.status_code == 200
    assert read.json()["enabled"] is True

    # 非法通道
    bad = await client.put(
        "/api/v1/settings/push",
        json={"channel": "telegram", "endpoint": "https://t.me/bot", "enabled": True},
        headers=headers,
    )
    assert bad.status_code == 422

    # 测试按钮（mock 推送成功）
    with patch("app.api.v1.push_settings.send_push", new_callable=AsyncMock) as mock_push:
        mock_push.return_value = True
        test = await client.post("/api/v1/settings/push/test", headers=headers)
    assert test.status_code == 200
    assert test.json()["delivered"] is True


async def test_push_test_without_config(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "push_bare")
    resp = await client.post("/api/v1/settings/push/test", headers=_auth(user_id))
    assert resp.status_code == 400


# ---------- 适配器（mock httpx，零网络） ----------


async def test_send_push_bark() -> None:
    from app.services.push import send_push

    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        ok = await send_push("bark", "https://api.day.app/key", "标题", "内容")
    assert ok is True


async def test_send_push_pushplus() -> None:
    """PushPlus：code==200 判定 + code!=200 拒绝 + json 解析异常兜底。"""
    from app.services.push import send_push

    # 成功
    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"code": 200, "msg": "ok"}
        assert await send_push("pushplus", "https://www.pushplus.plus/send/token", "t", "b") is True

    # 业务码失败
    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"code": 500, "msg": "额度不足"}
        assert (
            await send_push("pushplus", "https://www.pushplus.plus/send/token", "t", "b") is False
        )

    # json 解析炸（send_push 的 blanket except 兜底为 False）
    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: (_ for _ in ()).throw(ValueError("bad json"))
        assert (
            await send_push("pushplus", "https://www.pushplus.plus/send/token", "t", "b") is False
        )


async def test_send_push_wecom() -> None:
    """企微：errcode==0 判定 + errcode!=0 拒绝。"""
    from app.services.push import send_push

    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"errcode": 0}
        assert (
            await send_push(
                "wecom_webhook", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x", "t", "b"
            )
            is True
        )

    with patch("app.services.push._HTTP.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"errcode": 40001, "errmsg": "invalid key"}
        assert (
            await send_push(
                "wecom_webhook", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x", "t", "b"
            )
            is False
        )


async def test_send_push_never_raises() -> None:
    """send_push 永不抛异常的契约：底层全炸也返回 False。"""
    from app.services.push import send_push

    async def _explode(*args: object, **kwargs: object) -> None:
        raise ConnectionError("network down")

    with patch("app.services.push._HTTP.post", side_effect=_explode):
        assert await send_push("bark", "https://api.day.app/key", "标题", "内容") is False


async def test_send_push_unknown_channel() -> None:
    from app.services.push import send_push

    assert await send_push("telegram", "https://t.me/x", "标题", "内容") is False


def test_validate_push_config() -> None:
    assert validate_push_config("bark", "https://api.day.app/key") is None
    assert validate_push_config("bad", "https://x.com") is not None
    assert validate_push_config("bark", "not-a-url") is not None


# ---------- notify_and_push 一体化 ----------


async def test_notify_and_push_writes_notification_and_pushes(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """配置了推送通道的用户：通知落库 + 推送发出（mock）；未配置用户：只落库。"""
    pushed_user = await _create_user(engine, "pushed_user")
    bare_user = await _create_user(engine, "push_bare2")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    # 给 pushed_user 配推送
    async with maker() as session:
        await PushSettingsRepository(session).upsert(
            pushed_user, "bark", "https://api.day.app/test", True
        )
        await session.commit()

    push_calls: list[tuple[str, str, str]] = []

    async def fake_send_push(channel: str, endpoint: str, title: str, body: str) -> bool:
        push_calls.append((channel, title, body))
        return True

    with patch("app.services.push.send_push", side_effect=fake_send_push):
        async with maker() as session:
            await notify_and_push(
                session,
                pushed_user,
                NotificationType.MORNING_BRIEF,
                "早上好，今天 3 件事",
                "1. A\n2. B",
            )
            await session.commit()
            await notify_and_push(
                session, bare_user, NotificationType.MORNING_BRIEF, "早上好", "还没有安排"
            )
            await session.commit()

    # 两个用户的通知都落库了
    async with maker() as session:
        pushed_notifs = await NotificationRepository(session).list_for_user(pushed_user)
        bare_notifs = await NotificationRepository(session).list_for_user(bare_user)
    assert len(pushed_notifs) == 1
    assert len(bare_notifs) == 1

    # 只有配置了推送的用户触发了一次 send_push
    assert len(push_calls) == 1
    assert push_calls[0][0] == "bark"
    assert "3 件事" in push_calls[0][1]
