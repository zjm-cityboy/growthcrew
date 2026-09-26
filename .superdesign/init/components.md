# Shared UI Components

## 现状

前端为 create-next-app 脚手架（Next.js 16 + React 19 + Tailwind v4），**尚无任何共享 UI 组件**——无 `src/components/` 目录，无组件库依赖。

## 计划（见 docs/00-产品调研与技术方案.md）

- 组件库：shadcn/ui（P1 起按需引入）
- 首批自建组件：底部三 Tab 导航（今日/对话/档案）、任务卡片、卡因选择条、审批卡片
- 图表：ECharts（配置+渲染模式）

> 本文件随组件落地更新。设计稿先行，实现跟随设计稿。
