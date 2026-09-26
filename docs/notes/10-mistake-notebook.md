# 10 · 错题本与间隔复习（P4）

> 比喻：错题本是陪练的"小抄本"——每次你答错，他记下来；每天早晨提醒你翻一翻；答对了就隔更久再问，答错了明天接着问。记忆的本质是"在快要忘记的时候复习"。

## 一、为什么 P4 不需要 RAG

一道错题的题目本身就是**完整上下文**（不需要检索外部知识库）——直接喂给 LLM 就能出讲解。这是 ADR-0002"只在需要见机行事处用 Agent"的又一次体现：

| | 教练 Agent | 复盘师 Agent | **陪练（错题讲解）** |
|---|---|---|---|
| 编排 | LangGraph 图（有分叉） | 工具循环（纯线性） | **单次调用**（连工具都不需要） |
| 工具 | 4 个（含排程算法） | 4 个（含统计钻取） | **0 个** |
| 为什么 | 超载→自调重排 | 钻取顺序临场定 | 题目即全部上下文 |

**面试一句话**："我的三个 LLM 调用场景用了三种编排粒度：LangGraph 图、FastMCP 工具循环、单次调用——粒度递减，因为 Agent 性需求递减。错题讲解连工具都不需要，题目本身就是完整上下文。"

## 二、间隔复习：简化 SM-2

```python
# 答对：间隔翻倍
interval = min(interval * 2, 32)
# 连续 5 次答对 → 掌握（不再出现在复习队列）
if review_count >= 5: mastered = True

# 答错：重置
interval = 1
review_count = 0  # 连续计数清零

# 下次复习日 = 今天 + interval
next_review_at = today + timedelta(days=interval)
```

**间隔序列**：1 → 2 → 4 → 8 → 16 → 32（掌握）——记忆心理学依据：间隔递增比固定间隔的长期记忆效果好 2-3 倍（Ebbinghaus 遗忘曲线 + Spacing Effect）。

## 三、晨推集成（一行改动）

```python
# briefs.py 的 morning_brief_job 里加了一行查询
due = await MistakeRepository(session).count_due(user.id, today_cn())
title, body = render_morning_brief(today, due)

# render_morning_brief 的输出变化：
# 有任务 + 有错题："早上好，今天 3件事，2 道错题"
# 只有错题：      "早上好，2 道错题到期"
```

**产品理念贯彻**：不制造焦虑——错题用 📖 图标温和提醒，不用红色感叹号。

## 四、无 BYOK 时的优雅降级

```python
try:
    backend = await self._resolve_backend(user_id)
except LLMSettingsError:
    backend = None  # BYOK 未配置：保存题目但不生成讲解
```

题目照存（用户不会因为没配模型就丢失错题），讲解列填占位文案，配好模型后可重新录入触发讲解。**"功能降级但不失效"**是 BYOK 架构的关键设计原则。

## 五、面试追问预案（5 连）

1. **间隔复习算法为什么不用标准 SM-2？** 标准 SM-2 有 ease factor 和 quality rating（0-5 分），对打卡场景过重——用户只答"对/错"二选一。简化版（答对翻倍/答错重置/5 次掌握）行为等价且交互极简；
2. **错题讲解为什么不用 RAG？** 题目本身是完整上下文——不需要检索外部知识库。P5 的"专业问答"才需要 RAG（用户问的是开放性问题，需要从用户自己的知识库里找依据）；
4. **怎么保证复习的间隔准确？** `next_review_at` 是 Date 列有索引；`count_due` 查 `<= today AND mastered=false`，一天只查一次（晨推时）；`list_due` 限制 20 条防弹窗轰炸；
5. **掌握后的错题去哪了？** `mastered=True` 后不再出现在复习队列和晨推；列表页单独展示"已掌握"分区（前端 P4.e 实现）；
5. **如果用户想重新复习已掌握的题？** 可以后续加 `POST /mistakes/{id}/reset` 重置 mastery——目前 V1 没做（产品判断：掌握后重温价值低，不做比做了更好）。
