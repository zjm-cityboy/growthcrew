# 07 · 推送通道适配器（P2.3）

> 比喻：三个推送通道 = 三家快递公司（Bark 专送 iOS、PushPlus 走微信服务号、企微走群机器人）；`send_push` 是统一的前台收件口；`notify_and_push` 是"写通知表+叫快递"的一体化流程。

## 一、适配器模式的输入形状

```python
# 统一入口
async def send_push(channel: str, endpoint: str, title: str, body: str) -> bool:
    """返回 True=送达 / False=失败 / 永不抛异常"""

# 三家快递的差异化协议
Bark:      POST <endpoint> {"title": ..., "body": ..., "group": ...}
PushPlus:  POST <endpoint> {"title": ..., "content": ..., "template": "html"}
           → 返回 {"code": 200} 或 {"code": 500}
企微:      POST <endpoint> {"msgtype": "markdown", "markdown": {"content": ...}}
           → 返回 {"errcode": 0} 或 {"errcode": 非0}
```

**面试一句话**："适配器模式的判断点：三个通道的请求/响应协议各不相同（HTTP 状态码/业务码字段不同），但调用方（定时任务）不需要知道差异——`send_push(channel, ...)` 统一入口，加新通道只改一个函数。"

## 二、`notify_and_push`：通知是主体，推送是增益

```python
async def notify_and_push(session, user_id, type, title, body) -> bool:
    await NotificationRepository(session).create(...)   # ① 写通知表（主体）
    push_row = await PushSettingsRepository(session).get_by_user(user_id)
    if push_row and push_row.enabled:
        await send_push(push_row.channel, ...)           # ② 推送（增益，永不拖死①）
    return True
```

**设计要点**：
- 推送失败不影响通知落库（通知表是唯一事实源）；
- 推送超时 10s：定时任务批量跑 N 个用户，不能让一家快递拖死全队；
- `send_push` 的 `except Exception: return False` 契约让 job 层不需要 try/except；
- 未配置推送的用户静默走纯通知路径。

## 三、第八轮审查的 P0：httpx 依赖位置错误

**现象**：httpx 写在 `[dev]` extras 里（注释还是"测试客户端"），但 `services/push.py` 在生产代码中无条件 `import httpx`——Docker 镜像 `pip install .` 不装任何 extras → `ModuleNotFoundError: httpx`，**容器无法启动**。

**为什么 71 个测试全绿没发现**：开发环境必然装了 `[dev]`（pytest 依赖 httpx），所以本地永远有——**这类"依赖位置错误"只有干净安装才能暴露**。CI 的 `pip install -e ".[dev,agents,jobs]"` 也一样会掩盖。

**修法**：一行——`httpx>=0.28` 从 `[dev]` 移入 `[project].dependencies`，注释改为"推送适配器 + 测试客户端"。

**面试一句话**："我犯过一次依赖位置错误：httpx 写在 dev extras 但被生产代码引用，Docker 镜像直接起不来。根因是开发环境和 CI 都装了全部 extras，掩盖了基础安装的缺失。修法是把依赖移到主列表——教训是**生产依赖和生产代码必须在同一层**。"

## 四、httpx INFO 日志绕过脱敏（第八轮 P1）

**问题**：httpx 自身在 INFO 级输出完整请求 URL（含 device_key/token），项目自己的 `_mask_endpoint` 只覆盖自己那行日志——任何把 httpx logger 设为 INFO 的部署（接日志采集器等常见做法）会全量泄漏 token。

**修法**：一行——`logging.getLogger("httpx").setLevel(logging.WARNING)`。

**面试一句话**："日志脱敏不只是自己的代码——第三方库的内置日志也可能泄漏。我在推送适配器里发现 httpx 会在 INFO 级记录完整 URL，包括用户的 device_key。修法是把 httpx logger 拉到 WARNING。"

## 五、面试追问预案（5 连）

1. **为什么选这三家？** Bark 是 iOS 最可靠的自托管推送（APNs 级送达）；PushPlus 是国内微信生态免费方案（200 条/天够用）；企微 webhook 完全免费且配置最简——三家覆盖 iOS/微信/桌面三个场景；
2. **推送失败怎么办？** 通知表是唯一事实源，推送是增益层——失败只记日志返回 False，永不拖死定时任务；
3. **怎么防止用户配了 SSRF？** 单用户自托管场景下不构成威胁（用户配的 URL 打自己）；多租户部署时需解析后拒私网 CIDR（列为已知限制）；
4. **适配器模式在哪体现了开闭原则？** 加新通道（如 Telegram/钉钉）只需在 `send_push` 里加一个 `_send_xxx` 分支，调用方（jobs/API）零改动——对扩展开放、对修改关闭（只改一个函数）；
5. **怎么测试？** 两层 mock：patch `_HTTP.post` 测适配器协议判断（PushPlus code==200、企微 errcode==0）；patch `send_push` 测路由接线与 notify_and_push 门控。CI 零网络。
