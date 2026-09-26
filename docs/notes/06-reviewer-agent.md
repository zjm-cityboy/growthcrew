# 06 · 复盘师 Agent 与数据钻取（P2.2）

> 比喻：教练是排班编辑，复盘师是**数据记者**——采访三个数据源（完成统计/卡因分布/时段模式），然后写稿交编（submit_report 落库）。教练有分叉要问路（LangGraph 图），记者的路径自己定（工具循环），不需要图。

## 一、本篇核心：教练 vs 复盘师的架构对比（面试杀手锏）

| | 教练 Agent | 复盘师 Agent |
|---|---|---|
| 流程特征 | 有分叉：缺截止日/时长 → 提前返回追问（不触 LLM） | 纯线性：拿数据→写报告 |
| 编排 | **LangGraph StateGraph**（3 节点 + 条件边） | **不上图**，async 函数 + FastMCP 工具循环 |
| Agent 性 | 超载→自调→重排（模型临场决定） | 钻哪层数据由模型临场决定（有跳过才查卡因，有卡因才查时段） |
| Agent 性在哪一层 | 图的边 + 节点内部循环 | 循环本身 |

**面试一句话**："两个 Agent 两种编排：有分叉用图（LangGraph），纯线性直接函数+工具循环。Agent 性不来自框架，来自工具循环里模型的临场决策。"

## 二、复盘师的工具箱（FastMCP 注册，四件套）

| 工具 | 干什么 | 数据来源 |
|---|---|---|
| `get_week_stats` | 本周完成/总数/完成率 + 有活动天数 | `StatsService.trends(weeks=1)` + `StatsRepository.daily_status_counts` |
| `get_skip_reasons` | 卡因分布 [{reason, count, pct}] | `StatsService.skip_reasons`（**周界对齐**：从周一起算，不是死板 7 天） |
| `get_hour_patterns` | 24h 完成/跳过直方图 | `StatsService.hours`（同上） |
| `submit_report` | **校验先行**落库 + 写通知 | `WeeklyReportRepository.upsert` |

校验（全部有测试锁定）：
- `week_stats` 不在快照 → 拒绝（防模型跳过取数空写）；
- 标题 ≤195 字（留 5 字余量给通知前缀，防 PG VARCHAR(200) 溢出）；
- 正文 30-5000 字。

## 三、三个审查修复的故事（面试"你踩过什么坑"素材）

### 修复 1：days_with_activity 双重错位（第七轮 P1-1）
最初 `len(done_dates)` 数的是 `(date, status)` 组合数——一周 5 天各有 done+todo 得出 10 而非 5；且把纯排程日（todo 还没做）也算进去了。正确：按日期去重 + 只算 `status in (DONE, SKIPPED)`。**教训：喂给 LLM 的事实数据先测再上——模型会把这个错数当真相写进周报。**

### 修复 2：通知标题溢出只在 PG 炸（第七轮 P1-2）
报告标题截到 200 + 通知前缀"本周周报："（5 字）= 205 → SQLite 不校验 VARCHAR 长度全绿；PG VARCHAR(200) DataError → 500 → 报告本体一并回滚。**教训：长度约束的余量要算上拼接前缀。**

### 修复 3：周窗口从"近 7 天"改为"周界对齐"（第七轮 P2-1）
`window_days=7` 实际覆盖 today-7..today 共 8 天，周日跑周报时上周日的跳过混进来。改为 `(today - week_start).days + 1`。**教训：自然语言说"本周"，代码要落到"从周一起算"。**

## 四、与教练共享的 Agent 基础设施

- **LLMBackend 协议**：同一个 `complete(messages, tools, forced_tool)` 接口，FakeBackend 注入测试（CI 零网络零 token）；
- **BYOK 链路**：同一个 `LLMSettingsService.resolve` → `build_backend_from_byok`；未配置 → LLMSettingsError(400)；
- **异常翻译**：service 层把 `ReviewerError/LLMCallError` → `ReviewFailedError` → API 映射 502；
- **定时任务范式**：当日去重 + 单点隔离 + per-user commit/rollback；**新增一层**：BYOK 密钥失效（CryptoError）→ 静默跳过不计失败（不算任务错误，是用户侧配置问题）。

## 五、周三小结：不需要工具循环

半周小结只有三个数（本周至今 done/total、streak、今日剩余待办），数据全内联在 user message 里，**单次 LLM 调用直接出文案**——比工具循环少 3-4 次模型调用。这也是"只在需要时用工具"原则的体现：三个数不值得开工具循环。

## 六、面试追问预案（6 连）

1. **为什么复盘师不用 LangGraph？** 没有分叉就不需要图。工具循环本身已提供 Agent 性（钻取顺序临场定）。用图是过度设计；
2. **怎么防止 LLM 在周报里编数据？** 三层：system prompt 软约束 + submit_report 硬校验快照非空 + data_snapshot 存档事后审计（当时的原始数据永远可回看比对）。正文数字与工具数据的一致性做不了可靠硬校验（自然语言比对必误伤）——这是诚实的"能做到哪一步"；
3. **周报的口径和今日页一致吗？** 共享 `COUNTED_PLAN_STATUSES` 常量（domain/constants.py 单一事实源）；
4. **手动生成和定时任务并发跑怎么办？** `(user_id, week_start)` 唯一约束 + upsert：并发首写撞约束后 rollback→重查→走更新分支。代价是可能双份 LLM 调用（last-write-wins），可接受；
5. **两个 Agent 的测试怎么区分？** 教练用 FakeBackend 脚本（6 连工具调用回放）；复盘师同样——脚本是"工具调用序列"而非"文本回复"，验证的是编排逻辑而非文采；
6. **如果要把复盘师改成"先给结论再钻取证据"的深度模式？** 工具箱加一个 `get_task_list(date_range)` 让模型自行抽查具体任务——现在的三层钻取（汇总→卡因→时段）是预设路径，深度模式让模型选样本，工具层不用改架构。
