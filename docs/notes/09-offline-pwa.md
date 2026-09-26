# 09 · 数据导出 / PWA / 离线队列（P3 加固）

> 比喻：P3 是给房子做防水——功能都已就位，现在要保证"下雨天（断网/Excel/暗色）也不漏水"。

## 一、数据导出：不只是"能导"

三个坑连着踩（第十轮审查 P1+P2）：

### 1. CSV 公式注入
用户可控文本（目标标题、任务名、感想、周报正文）以 `=`/`+`/`-`/`@` 开头时，Excel 会当公式执行。我们自己的 section 头 `=== 目标 ===` 都以 `=` 开头——先中招了。

**修法**：`_safe()` 函数对以这六个字符开头的单元格加 `'` 前缀（OWASP 标准）；section 头改 `## 目标 ##`。有测试锁定。

### 2. UTF-8 BOM
中文内容 + UTF-8 + 无 BOM → Windows Excel 按 GBK 解码 → 一片乱码。"数据主权"导出实际不可用。

**修法**：`output.write("\ufeff")` 一行。有测试锁定。

### 3. 前端下载链接绕过 api.ts 的 token 管理
裸 `JSON.parse(localStorage)` + 不检查 `resp.ok` → token 过期时用户拿到内容是 401 JSON 的"CSV"。

**修法**：改用 `loadTokens()`（有脏数据自愈）+ `resp.ok` 检查 + 错误 alert。

## 二、PWA：manifest + Service Worker

```
manifest.ts → Next.js 自动生成 /manifest.webmanifest
sw.js      → 手动注册（ClientInit 组件）
```

**Service Worker 缓存策略**：
- 只缓存 GET 请求；
- `/api/` 路径不缓存（跨源 API 也不缓存）；
- **网络优先**（在线时拿到最新），失败回缓存（离线兜底）；
- 无缓存时回 `/`（SPA 兜底）。

**Server/Client 拆分**（踩坑）：`metadata` 导出必须在 Server Component，`useEffect` 必须在 Client Component——根布局不能同时干两件事。拆成 `layout.tsx`（Server）+ `ClientInit.tsx`（Client，挂 SW 注册和离线队列监听）。

## 三、离线打卡队列（P3 核心交付）

```
断网 → api.completeTask 抛 ApiError(status=0) → enqueueOffline() → localStorage
联网 → window online 事件 / 页面加载 → syncOfflineQueue() → 按序补传 → 通知刷新
```

### 第十轮审查的 P0：401 丢队列

**问题**：access_token 只有 15 分钟。断网 >15 分钟后恢复联网（这正是"自习室地下室"的目标场景），补传时 token 必然过期 → 401 → 原实现直接丢弃全部队列——**核心承诺在最典型路径下失效**。

**修法**：401 时先调 `/auth/refresh` 拿新 token 重试一次（复用 refresh_token，30 天有效）；refresh 也失败才清登录态跳转 /login。

### P1：无加载时触发

`online` 事件只在"页面打开期间由断网变联网"时触发。用户断网打卡→关页面→重新打开应用（最常见恢复路径），无触发点。

**修法**：`registerOfflineQueueSync()` 末尾加 `void sync()`——页面加载即补传。

## 四、暗色模式图表适配

```typescript
function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}
export function chartColors() {
  return { accent: cssVar("--gc-accent", "#5C8A6E"), ... };
}
```

**关键**：ECharts 的 SVG renderer 不解析 CSS 变量（`stroke="var(--gc-bg)"` 无效），必须用 `getComputedStyle` 读计算后的具体色值。局限性：主题切换后需刷新页面图表才更新（可接受）。

## 五、面试追问预案（5 连）

1. **离线队列怎么保证数据不丢？** localStorage 持久化 + 401 时刷新 token 重试 + 409/422 幂等处理（已完成再打卡=成功）+ 重试上限 3 次 + 队列上限 50 条（丢最旧——打卡是时效性数据）；
2. **CSV 注入是什么？** 用户可控文本以 `=` 等开头时 Excel 当公式执行，可能泄漏文件内容或执行恶意公式。OWASP 修法是加 `'` 前缀；
3. **Service Worker 的缓存策略？** 网络优先 + 离线回缓存——数据要新鲜（在线拿最新），但断网时页面可用（回缓存）。API 路径不缓存（需要实时数据）；
4. **PWA 的 manifest 做了什么？** `display: standalone` 让 PWA 从浏览器标签页变成独立应用窗口；`theme_color` 让地址栏/状态栏跟随品牌色；配合 Service Worker 实现"添加到主屏幕"后离线可用；
5. **暗色模式图表怎么适配？** ECharts 不走 CSS 变量，用 `getComputedStyle` 读令牌计算值。主题切换后需刷新——代价可接受。
