"""认证全流程测试：注册/登录/受保护接口/刷新轮换。"""

from httpx import AsyncClient

_REGISTER = {"username": "student_01", "password": "super-secret-1"}


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(client: AsyncClient) -> dict[str, str]:
    reg = await client.post("/api/v1/auth/register", json=_REGISTER)
    assert reg.status_code == 201
    login = await client.post("/api/v1/auth/login", json=_REGISTER)
    assert login.status_code == 200
    return login.json()


async def test_register_login_me(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)

    me = await client.get("/api/v1/auth/me", headers=_auth_header(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == _REGISTER["username"]


async def test_register_duplicate_username(client: AsyncClient) -> None:
    first = await client.post("/api/v1/auth/register", json=_REGISTER)
    assert first.status_code == 201
    second = await client.post("/api/v1/auth/register", json=_REGISTER)
    assert second.status_code == 409


async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "student_01", "password": "short"}
    )
    assert resp.status_code == 422


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=_REGISTER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _REGISTER["username"], "password": "wrong-password!"},
    )
    assert resp.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_login_rate_limited(client: AsyncClient) -> None:
    """同一 IP 连续失败登录超过阈值后应 429，并带 Retry-After 头。"""
    await client.post("/api/v1/auth/register", json=_REGISTER)
    for _ in range(10):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": _REGISTER["username"], "password": "wrong-password!"},
        )
        assert resp.status_code == 401
    blocked = await client.post("/api/v1/auth/login", json=_REGISTER)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after") == "60"


async def test_register_rate_limited(client: AsyncClient) -> None:
    """注册接口每 IP 每分钟限 3 次（argon2 是 CPU 密集型无认证接口）。"""
    for i in range(3):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": f"user_{i:02d}", "password": "super-secret-1"},
        )
        assert resp.status_code == 201
    fourth = await client.post(
        "/api/v1/auth/register", json={"username": "user_99", "password": "super-secret-1"}
    )
    assert fourth.status_code == 429


async def test_refresh_rotation(client: AsyncClient) -> None:
    """刷新令牌必须旋转：换新对之后，旧 refresh 不能再用。"""
    tokens = await _register_and_login(client)

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    me = await client.get("/api/v1/auth/me", headers=_auth_header(new_tokens["access_token"]))
    assert me.status_code == 200
