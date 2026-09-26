# ADR-0004：前端令牌存 localStorage（当前取舍与迁移条件）

日期：2026-09-23 · 状态：已采纳（带明确的迁移触发条件）

## 决策

P1.4 前端将 JWT（access + refresh）存于 `localStorage`，API 客户端内置 401 单飞刷新与重试。

## 理由

1. 自托管单页应用、无第三方脚本（无统计/广告 SDK），XSS 注入面当前很小；
2. 实现最简，PWA 场景下 service worker 与 fetch 拦截都好接；
3. 后端 refresh 已做旋转 + 服务端可检测重放。

## 已知债务与迁移条件（满足任一即迁 httpOnly cookie + CSRF 防护或 BFF 代理）

- 引入任何第三方 JS（统计、客服、SDK）之前——必须先迁移；
- 开放多用户注册（不再是熟人自托管）之前；
- 出现任何 XSS 修复记录。

## 相关待办

- ~~logout 只清本地~~ → **已清偿（P2.1）**：`POST /auth/logout` 服务端撤销全部 refresh token（`RefreshTokenRepository.revoke_all_for_user`，原子 UPDATE），测试覆盖"登出后旧 refresh 重放 401"。

## 被否方案

- httpOnly cookie（当前）：需后端 CSRF 改造 + SameSite 策略，P1.4 收益不成立；
- 内存 only：PWA 重开即掉登录态，体验不可接受。
