"""推送通道适配器：Bark / PushPlus / 企微 webhook（httpx，统一接口）。

设计要点：
- 适配器模式：send_push(channel, endpoint, title, body) 统一入口，
  内部按 channel 分发到具体实现——加新通道只改一个函数；
- 超时 10s：推送是"尽力而为"（通知表已有持久记录），不能拖死定时任务；
- 永远不抛异常：失败记日志返回 False，调用方（job）不需要 try/except；
- endpoint 是完整 URL（含 device_key/token/webhook key），用户从设置页粘贴。
- notify_and_push：定时任务用的"写通知 + 推送"一体化辅助（推送失败不影响通知落库）。
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import NotificationType
from app.repositories.notification import NotificationRepository
from app.repositories.push import PushSettingsRepository

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_HTTP = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
# httpx 自身在 INFO 级记录完整请求 URL（含 device_key/token），会绕过 _mask_endpoint 的脱敏
logging.getLogger("httpx").setLevel(logging.WARNING)

_PUSH_CHANNELS = ("bark", "pushplus", "wecom_webhook")


async def send_push(channel: str, endpoint: str, title: str, body: str) -> bool:
    """统一推送入口。返回 True=送达 False=失败（永不抛异常）。"""
    try:
        if channel == "bark":
            return await _send_bark(endpoint, title, body)
        if channel == "pushplus":
            return await _send_pushplus(endpoint, title, body)
        if channel == "wecom_webhook":
            return await _send_wecom(endpoint, title, body)
        logger.warning("未知推送通道 %r", channel)
        return False
    except Exception:
        logger.exception("推送异常 channel=%s endpoint=%s", channel, _mask_endpoint(endpoint))
        return False


async def notify_and_push(
    session: AsyncSession, user_id: int, type: NotificationType, title: str, body: str
) -> bool:
    """定时任务用的"写通知 + 推送"一体化。推送失败不影响通知落库。

    返回 True=通知已写入（推送结果不影响返回值——通知是主体，推送是增益）。
    """
    await NotificationRepository(session).create(user_id=user_id, type=type, title=title, body=body)

    push_row = await PushSettingsRepository(session).get_by_user(user_id)
    if push_row is not None and push_row.enabled:
        await send_push(push_row.channel, push_row.endpoint, title, body)

    return True


async def _send_bark(endpoint: str, title: str, body: str) -> bool:
    """Bark（iOS）：POST <endpoint> JSON。"""
    resp = await _HTTP.post(endpoint, json={"title": title, "body": body, "group": "growthcrew"})
    ok = resp.status_code == 200
    if not ok:
        logger.warning("Bark 推送失败 %d: %s", resp.status_code, resp.text[:200])
    return ok


async def _send_pushplus(endpoint: str, title: str, body: str) -> bool:
    """PushPlus（微信服务号）：POST <endpoint> JSON {title, content, template}."""
    resp = await _HTTP.post(endpoint, json={"title": title, "content": body, "template": "html"})
    data = resp.json() if resp.status_code == 200 else {}
    ok = resp.status_code == 200 and data.get("code") == 200
    if not ok:
        logger.warning("PushPlus 推送失败 %s: %s", resp.status_code, str(data)[:200])
    return ok


async def _send_wecom(endpoint: str, title: str, body: str) -> bool:
    """企微群机器人 webhook：POST <endpoint> JSON {msgtype: markdown}."""
    markdown = f"**{title}**\n\n{body}"
    resp = await _HTTP.post(
        endpoint, json={"msgtype": "markdown", "markdown": {"content": markdown}}
    )
    data = resp.json() if resp.status_code == 200 else {}
    ok = resp.status_code == 200 and data.get("errcode") == 0
    if not ok:
        logger.warning("企微推送失败 %s: %s", resp.status_code, str(data)[:200])
    return ok


def _mask_endpoint(endpoint: str) -> str:
    """日志脱敏：只保留前 30 后 10 字符（含 device_key/token 的 URL 不全打）。"""
    if len(endpoint) <= 40:
        return endpoint[:10] + "…"
    return endpoint[:30] + "…" + endpoint[-10:]


def validate_push_config(channel: str, endpoint: str) -> str | None:
    """校验推送配置，返回错误消息或 None（通过）。含 SSRF 防护。"""
    if channel not in _PUSH_CHANNELS:
        return f"通道仅支持 {'/'.join(_PUSH_CHANNELS)}"
    if not endpoint.startswith(("https://", "http://")):
        return "端点必须是完整 URL（以 https:// 开头）"
    if len(endpoint) > 500:
        return "端点过长（≤500 字符）"
    # SSRF 防护：拒私网/环回/链路本地/保留地址（安全 M-1）
    ssrf_error = _validate_no_private_address(endpoint)
    if ssrf_error:
        return ssrf_error
    return None


def _validate_no_private_address(url: str) -> str | None:
    """解析 URL 主机名，拒绝指向私网/环回/元数据的地址。"""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "URL 缺少主机名"
        # 尝试直接解析为 IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return "端点不能指向内网/本机地址"
            return None
        except ValueError:
            pass  # 不是 IP 字面量，继续做 DNS 解析
        # DNS 解析后逐个检查
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return None  # 解析失败不阻止（可能是临时 DNS 问题），让请求自身报错
        for addr_info in addr_infos:
            ip = ipaddress.ip_address(addr_info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return f"域名 {hostname} 解析到内网地址 {ip}，不允许"
        return None
    except Exception:
        return None  # 解析异常不阻止保存（防止误拦合法配置）
