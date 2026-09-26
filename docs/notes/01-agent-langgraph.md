# 01 · 教练 Agent 与 LangGraph 精讲

> 比喻主线：GrowthCrew 是一支编辑部小团队，教练是新入职的"排班编辑"。
> 方法论：**输入形状视角**——先看官方 API 长什么样，再看我们的调用怎么对上去（和 harness 备菜链笔记同一套）。

## 一、LangGraph 官方 API 的"输入形状"

LangGraph 全部核心就 6 个函数/类的形状：

| 官方形状 | 作用 | 人话 |
|---|---|---|
| `StateGraph(T)` | 用状态类型 T 建图 | 拿到一张空白的车间平面图 |
| `graph.add_node(name, fn)` | 注册节点 | 摆一个工位，fn 是这个工位的活 |
| `graph.add_edge(a, b)` | 固定边 | 传送带：a 干完必去 b |
| `graph.add_conditional_edges(node, router, mapping)` | 条件边 | 质检员：看完工单决定下一站 |
| `graph.compile()` | 编译 | 图纸通电变成流水线 |
| `await graph.ainvoke(init_state)` | 执行 | 工单上产线，跑到 END 为止 |

节点 fn 的形状是统一的：**吃 state（dict），吐"补丁"（partial dict）**——框架自动把补丁 merge 进工单。就这一条约定，剩下的全是普通 Python。

## 二、State：那张贯穿全图的工单

```python
class PlannerState(TypedDict, total=False):   # ← TypedDict：带类型标注的普通 dict
    missing: list[str]                        # 缺失信息（gather 写，路由用）
    parsed_subjects: list[dict[str, Any]]     # 解析出的科目（parse 写，coach 读）
    parse_note: str                           # 解析备注（parse 写，仅记录）
```

逐行拆解：

- `TypedDict`：不是新数据结构，运行时就是 dict；LangGraph 读类型标注来认识这张工单的合法字段；
- `total=False`：**所有键可选**——所以入口敢传空工单 `ainvoke({})`。没有它，TypedDict 默认"所有键必须在"，第一站就得凑齐全部字段；
- **自动合并**：节点只返回自己写的那几格（如 `{"missing": []}`），框架 merge，其余键原封不动。

**什么进 State、什么走闭包（本项目最重要的设计判断）**：

> 判断标准只有一条：**路由要看的数据进 State，干活要用的材料走闭包。**

`raw_text`（贴入的原文）、`backend`（LLM 客户端）、`ctx`（工具共享状态）全走闭包——节点函数定义在 `_build_graph(raw_text, ...)` 内部，Python 闭包让它们"记住"外层变量。图不关心它们，所以工单干净。

## 三、三道工序（节点）

| 节点 | 干什么 | 读 | 写 |
|---|---|---|---|
| `gather` | 查目标缺不缺截止日/每周时长 | `self._goal`（闭包） | `{"missing": [...]}` |
| `parse` | LLM 强制结构化解析（`forced_tool` 钉死输出形状） | raw_text、backend（闭包） | `{"parsed_subjects": ...}` |
| `coach` | **Agent 时刻**：LLM 自主决定工具调用序列 | 闭包 + state 的科目 | `{}`（产物写进 ctx） |

`coach` 返回空补丁是刻意的：它的产物（提案 id）只被 `run()` 结束后读取，没有下游节点需要路由它——放 State 里就是噪音。

## 四、边的流向（图的骨架只有六行）

```python
graph.add_conditional_edges("gather", has_questions, {"questions": END, "parse": "parse"})
graph.add_edge(START, "gather")     # 入口
graph.add_edge("parse", "coach")    # 固定边
graph.add_edge("coach", END)        # 出口
```

条件边三件套（面试高频）：**①起点**（从哪分流）**②路由函数**（吃 state 返回下一站的"名字字符串"）**③映射表**（名字 → 真实目的地）。我们的路由函数就一行：

```python
def has_questions(state: PlannerState) -> str:
    return "questions" if state.get("missing") else "parse"
```

流向图：

```
START → gather ─┬─ missing 非空 → END（返回追问，LLM 零调用）
                └─ missing 为空 → parse → coach → END（提案待审批）
```

## 五、coach 节点内部：真正的"Agent 性"

工具循环的消息形状（OpenAI chat completions 格式）：

```
[system 教练人设与规则] → [user 目标+预算+原文]
→ assistant(tool_calls: get_goal_context)   ← 模型自己决定的
→ tool(结果 JSON)
→ assistant(tool_calls: schedule_week 18h)  → tool(结果: overloaded=true!)
→ assistant(tool_calls: schedule_week 10h)  → tool(结果: 不超载)     ← 看到超载自调重排
→ assistant(tool_calls: submit_proposal)    → tool(提案已建, 等审批)
```

关键代码形状（`_coach_loop`）：

```python
async with Client(mcp) as client:                    # FastMCP 进程内客户端
    tools = [给每个工具拼 OpenAI schema]               # 从 client.list_tools() 读 t.input_schema
    for _ in range(6):                                # 上限 6 轮（防失控）
        result = await self._backend.complete(messages, tools)
        if not result.tool_calls: break               # 模型不调工具了 = 收工
        messages.append(助手消息含 tool_calls)          # 消息历史自己维护
        for call in result.tool_calls:
            data = (await client.call_tool(call.name, call.arguments)).data
            messages.append({"role": "tool", "tool_call_id": call.id, ...})
        if self._ctx.proposal_id is not None: break   # 提案落地即出循环
```

两个防御（审查轮加的）：工具执行异常 → `logger.exception` 记全量 + 只回喂 `{"error": ...}` 给模型自行纠正；`submit_proposal` 校验先行（≤50 条、时长 1-240、日期合法，全过才建计划——失败重试不留孤儿草稿，有回归测试）。

## 六、为什么没有 `__interrupt__`（对齐 harness 经验）

harness 用 interrupt 把图挂起等人审批，靠 checkpointer 跨请求续跑。这里**故意不用**（ADR-0003）：审批暂停落在 `plan_proposals` 表（服务层确定性 approve/reject，条件 UPDATE 原子防并发双批），因为图节点闭包持有请求 A 的 DB 会话，请求 B 恢复时该会话已关——跨请求共享会话的复杂度与收益不成比例，且提案表本身就是持久审计。一句话：**interrupt 适合"对话中插一嘴"，服务层审批适合"关掉 App 明天再批"**。P2 对话 Tab 的多轮会话才是 checkpointer 的主场。

## 七、面试追问预案（10 连）

1. **图这么小为什么用 LangGraph？** 流程即声明（改需求不漏分支）+ 节点独立可测 + P2 加复盘师/总编时骨架现成；也坦白：这规模 if/else 能写，选它是为演进与规范。
2. **State 和闭包怎么分？** 路由要看的进 State，材料走闭包（本篇二）。
3. **Agent 性体现在哪？** coach 里超载→自调→重排的路径是模型临场决定的，代码没写死；解析用 forced_tool 钉形状、排程是确定性算法——"只在见机行事处用 LLM"。
4. **排程为什么不让 LLM 算？** 精确计算交给算法（可测试、零成本、不会算错），LLM 只决定何时调用与如何解释。
5. **LLM 输出怎么防注入/防垃圾？** 四层：输入文本只进 user message 且截断；工具无 user_id 参数（写入全绑 ctx.goal）；工具参数全量校验（条数/时长/日期）；产物 DRAFT 态必须人审才生效。
6. **forced_tool 供应商不遵守怎么办？** 有防御：空 tool_calls/空 subjects → PlannerError → 502 业务错误（有测试），不是 500。
7. **工具为什么过 FastMCP？** 统一注册成带 schema 的工具（list_tools/call_tool 进程内调用零网络）；换对话型 Agent 时工具层直接复用。
8. **测试怎么保证零网络？** LLMBackend 协议 + FakeBackend 脚本回放（5 连调用逐条断言），CI 不花一个 token。
9. **和 harness 的 Agent 区别？** harness=审批工作流 interrupt 挂起；这里=单请求内编排+服务层审批——我论证过为什么后者更稳（ADR-0003）。
10. **如果并发导入同一目标？** weekly_plans 有 (goal_id, week_start, version) 唯一约束，submit_proposal 撞约束回滚重算一次。

## 八、动手验证

- `pytest tests/test_p12_agent.py -k questions -s`：看分叉路径不触达 LLM；
- gather 里加 `print(state)` 跑全量：亲眼看工单每步长什么样；
- 把 START 边改到 parse：测试的红法本身就是理解。
