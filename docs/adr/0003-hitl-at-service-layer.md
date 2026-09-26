# ADR-0003：P1.2 的 HITL 审批放在服务层，而非 LangGraph interrupt

日期：2026-09-23 · 状态：已采纳

## 背景

教练 Agent 的提案需要用户批准（HITL）。harness-erp 用 LangGraph `__interrupt__` 挂起图运行等待人工输入。本项目 P1.2 评估后发现直接照搬有工程问题。

## 决策

- **Agent 编排（LangGraph 图 + 工具循环）在一次 HTTP 请求内完成**；
- **审批暂停不依赖图的中断状态**：提案落库于 `plan_proposals`（PENDING），approve/reject 是确定性的服务层操作（落 ACTIVE、旧版 SUPERSEDED、写审计与通知）。

## 理由

1. interrupt 恢复要求图状态跨请求存活（checkpointer）。图节点闭包持有请求 A 的 DB 会话，请求 B 恢复时该会话已关闭——要么重构会话管理，要么引入序列化边界，P1.2 收益不成比例；
2. 提案表本身就是持久化审批记录（审计/回滚需求已在），双写图状态属冗余状态源；
3. 服务层审批对重启天然免疫：pending 提案永远可批，不会因进程重启丢失。

## 后果

- 引入跨请求多轮对话（P2 对话 Tab）时，需重新评估 checkpointer（langgraph-checkpoint-postgresql 届时再引入，当前依赖源无发行版）；
- "interrupt 级 HITL"的面试叙事改为"P1 论证了为什么服务层审批更可靠"——知道何时不用 interrupt 与会用 interrupt 同等有价值。

## 被否方案

- 照搬 harness 的 interrupt + MemorySaver：跨请求会话共享复杂、重启丢 pending 审批；
- 全流程不用 LangGraph：coach 节点的工具循环（超载→下调→重排）确属"见机行事"，图结构让节点职责与测试边界清晰。
