# Extractable Components（可提取组件菜单）

## 现状

脚手架阶段，**无可提取组件**。

## 计划提取（页面落地后）

- `BottomTabBar`（layout）— 底部三 Tab 导航：今日/对话/档案；props: `activeTab: "today" | "chat" | "archive"`
- `TaskCard`（basic）— 今日任务卡：勾选打卡、跳过+卡因四选一；props: `done: boolean`, `title: string`
- `ApprovalCard`（basic）— Agent 提案审批卡：要点+同意/拒绝；props: `kind: "plan" | "adjust"`
- `StreakBadge`（basic）— 连续天数徽章；props: `days: number`

> 设计稿确认后，按草稿反推组件实现，再更新本菜单。
