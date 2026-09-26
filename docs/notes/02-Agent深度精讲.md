# 02 · Agent 与 LangGraph 深度精讲

> 本篇覆盖：三种编排粒度对比、LangGraph 核心概念、工具循环、Agent 安全。

---

## 一、三种编排粒度对比（面试杀手锏 #1）

| | 教练 Agent | 复盘师 Agent | 陪练（错题） |
|---|---|---|---|
| 编排 | **LangGraph StateGraph** | **FastMCP 工具循环** | **单次 LLM 调用** |
| 工具数 | 4 | 4 | **0** |
| 为什么 | 有分叉（缺信息提前 END） | 纯线性但钻取临场定 | 题目即完整上下文 |
| Agent 性来源 | 图的边 + 节点内循环 | 循环本身（钻哪层临场定） | 不需要（一次性讲解） |

> **面试一句话**："粒度递减因为 Agent 性需求递减——错题讲解连工具都不需要。知道什么时候不用 Agent 比会用更值钱。"

## 二、LangGraph 核心

### State（工单）

```python
class PlannerState(TypedDict, total=False):
    missing: list[str]              # 路由用——gather 写、条件边读
    parsed_subjects: list[dict]     # parse 写、coach 读
```

关键点：
- `TypedDict`：运行时就是 dict，LangGraph 读类型标注认识合法字段
- `total=False`：所有键可选，入口 `ainvoke({})`
- **自动合并**：节点返回 partial dict → merge 进当前 state
- **设计判断**：路由要看的数据进 State，干活要用的材料走闭包

### 节点（工序）

| 节点 | 干什么 | 读 | 写 |
|---|---|---|---|
| `gather` | 查目标缺不缺截止日/时长 | `self._goal`（闭包） | `{"missing": [...]}` |
| `parse` | LLM 强制结构化解析 | raw_text、backend（闭包） | `{"parsed_subjects": ...}` |
| `coach` | **工具循环**（ReAct） | 闭包 + state | `{}`（产物写进 ctx） |

节点就是函数：`(state) -> partial dict`，同步或异步均可。

### 边（流向）

```python
graph.add_conditional_edges("gather", has_questions, {"questions": END, "parse": "parse"})
graph.add_edge(START, "gather")
graph.add_edge("parse", "coach")
graph.add_edge("coach", END)
```

条件边三件套：**①起点**（从哪分流）**②路由函数**（吃 state 返回下一站名字）**③映射表**（名字→目的地）。

```
START → gather ─┬─ missing 非空 → END（返回追问）
                └─ missing 为空 → parse → coach → END
```

### Checkpoint 与 interrupt（为什么我们不用）

| | LangGraph interrupt | 我们的服务层审批 |
|---|---|---|
| 实现 | 节点内 `interrupt()` → 图挂起 → checkpointer 存状态 | plan_proposals 表 + 条件 UPDATE |
| 恢复 | `Command(resume=value)` 从断点继续 | approve/reject API |
| 跨请求 | 需要 checkpointer + 跨请求会话管理 | 天然支持（数据在 DB） |
| 重启免疫 | MemorySaver 会丢 | **天然免疫** |
| 适用 | "对话中插一嘴" | "关掉 App 明天再批" |

## 三、工具循环详解（ReAct 模式）

### 消息流

```
[system 教练人设] → [user 目标+预算+原文]
→ assistant(tool_calls: get_goal_context)   ← 模型自己决定
→ tool(目标信息 JSON)
→ assistant(tool_calls: schedule_week 18h)  → tool(overloaded=true!)
→ assistant(tool_calls: schedule_week 10h)  → tool(不超载)     ← 看到超载自调重排
→ assistant(tool_calls: submit_proposal)    → tool(提案已建)
```

### 关键代码

```python
async with Client(mcp) as client:
    tools = [从 list_tools() 读 schema 并拼 OpenAI 格式]
    for _ in range(6):                    # 上限 6 轮防失控
        result = await backend.complete(messages, tools)
        if not result.tool_calls: break   # 模型不调工具了 = 收工
        messages.append(助手消息含 tool_calls)
        for call in result.tool_calls:
            data = (await client.call_tool(call.name, call.arguments)).data
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(data)})
        if ctx.proposal_id is not None: break  # 提案落地即出循环
```

**Agent 性在第②→③步**：看到超载后要不要下调、下调多少、要不要再排——是模型临场决定的，代码里没写死。

## 四、Agent 安全

### Prompt 注入防御四层

| 层 | 机制 |
|---|---|
| ① 输入隔离 | 贴入文本只进 user message，8000 字截断，用定界符包裹 |
| ② 工具无用户参数 | Agent 工具不接受 user_id/goal_id——写入全绑定启动时鉴权加载的 ctx.goal |
| ③ 输出过校验 | 工具参数全量校验（≤50 条/时长 1-240/日期合法）；LLM 输出经 Pydantic schema 才落库 |
| ④ HITL 兜底 | 产物 DRAFT 态必须人审才生效 |

### 写权限矩阵

| 数据 | Agent 权限 |
|---|---|
| 查询（读） | 自由 |
| 计划类 | 起草 → 人审 → 落库（版本化可回滚） |
| 历史事实（打卡/卡因） | **永不可写** |
| 密钥/账号 | 不可写 |

> **面试一句话**："Agent 可以修改未来的安排，不能篡改过去的事实。"

## 五、复盘师（为什么不上 LangGraph）

教练有分叉（缺信息提前 END）→ 用图；复盘师纯线性（拿数据→写报告）→ 直接 async 函数 + 工具循环。**图没有分叉就不需要图。**

工具循环本身提供 Agent 性：钻取顺序由模型临场决定（有跳过才查卡因，有卡因才查时段）。

## 六、BYOK 架构

```
用户配三件套（base_url + api_key + model_name）
→ api_key Fernet 加密落库（主密钥 = GC_ENCRYPTION_KEY 环境变量）
→ API 永不回明文（只回脱敏 sk-***abcd）
→ 构建 LLM 客户端时内存解密（微秒级，用完即丢）
→ BYOK 未配置时优雅降级（保存题目无讲解）
```

**面试一句话**："用户密钥 Fernet 加密落库，主密钥走独立环境变量，API 层永不回明文，解密只在构建 LLM 客户端那一瞬间——数据库被拖走也拿不到可用密钥。"
