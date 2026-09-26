# 05 · 统计聚合与档案数据 API（P2.1）

> 比喻：统计层 = 编辑部的**数据记者**——它不创作（那是复盘师 P2.2 的事），只把散落的打卡记录变成干净的表格。本篇讲"表格怎么算出来的"以及三个跨方言取舍。

## 一、四个统计端点的输入形状

| 端点 | 产出 | 前端用途 |
|---|---|---|
| `GET /stats/heatmap?weeks=8` | 每日 {done,total} 列表 | 打卡热力图（色阶按 rate） |
| `GET /stats/trends?weeks=8` | 每周 {done,total,rate} | 完成率竖条图 |
| `GET /stats/skip-reasons?days=90` | 卡因分布 [{reason,count,pct}] | "跳过的原因"横条 |
| `GET /stats/hours?days=90` | 24 桶完成/跳过直方图 | "你的高效时段"（P2.2 复盘师的数据源） |

Query 参数全部 `Query(ge=..., le=...)`——越界 422 在路由层就拦，不进业务。

## 二、取舍一：SQL 分组 vs Python 加工

**SQL 只做分组计数**（group by date/status、group by skip_reason），**周对齐和小时分桶放 Python**。为什么：

- 按周聚合在 SQL 里要 `date_trunc('week', ...)`（PG）vs `strftime('%W',...)`（SQLite）——跨方言不通用；
- 数据量级：90 天 × 每天≤3 件 = 最多几百行，拉回来在 Python 对齐成本可忽略；
- **代价（有意近似）**：hours/skip-reasons 窗口按 `Task.date`（排程日）过滤，"排程在窗口外、完成发生在窗口内"的边缘事件会漏——量级可忽略，第六轮审查确认接受。

```python
def _monday_of(day: date) -> date:           # 周对齐：ISO 周一
    return day - timedelta(days=day.weekday())
```

## 三、取舍二：小时分桶的时区口径

`completed_at` 落库是 UTC；直方图要按**北京时间小时**分桶（用户视角）。`_to_cn_hour` 的双库处理：

```python
def _to_cn_hour(value: datetime) -> int:
    if value.tzinfo is None:                  # SQLite 回读朴素值
        value = value.replace(tzinfo=ZoneInfo("UTC"))  # 按写入约定（UTC）补时区
    return value.astimezone(_CN_TZ).hour      # PG 回读 aware 值直接转
```

关键在"写入约定"：我们的服务端全部用 `datetime.now(UTC)` 写入，所以朴素值=UTC 这个假设全仓成立。测试用"北京 22:30 完成"钉死了这个行为（`test_hours_histogram_cn_timezone`）。

## 四、取舍三：口径的单一事实源

```python
# app/domain/constants.py
COUNTED_PLAN_STATUSES = [PlanStatus.ACTIVE, PlanStatus.SUPERSEDED]
```

统计只算"生效中 + 已替代"的计划（草稿/待审批用户根本看不见）；streak 对已替代版本保留（**历史事实不因计划迭代被抹掉**，distinct 日期天然去重）。最初这个常量藏在 repositories/plan.py 的私有名 `_COUNTED_PLAN_STATUSES`，被 stats.py 跨文件导入——第六轮审查指出"口径单一事实源不该靠下划线约定流转"，提升到 domain 层。

## 五、本篇的坑：`result.all()` 只能消费一次

```python
# 错误写法（第二个 all() 返回空列表！）
completed = [r[0] for r in result.all() if r[0] is not None]
skipped  = [r[1] for r in result.all() if r[1] is not None]   # 永远空

# 正确写法：先取回再抽取
rows = result.all()
completed = [r[0] for r in rows if r[0] is not None]
skipped  = [r[1] for r in rows if r[1] is not None]
```

SQLAlchemy 的 Result 是**游标式**的，`all()` 取尽后游标到底。这个 bug 测试全绿都发现不了吗？不——测试当场就红了（skip 桶为空），但它说明**"绿色测试"也依赖断言写对地方**：如果我只断言 completion 桶，它会静默通过。探针脚本（直接在内存库跑 repo 方法打印返回）是定位这类问题的最快路径。

## 六、登出撤销（一笔安全债的清偿）

ADR-0004 曾记录"logout 只清本地"的债务，本篇清偿：

```python
# 一条原子 UPDATE 撤销该用户全部有效 refresh
update(RefreshToken).where(user_id==, revoked.is_(False)).values(revoked=True)
```

语义要点：**幂等**（重复登出 rowcount=0 无害）、**原子**（无 check-then-write 窗口）、access token 残留 15 分钟是 JWT 无状态的固有窗口（安全笔记已如实记录）。前端配套：`request()` 补了 204 空响应体分支（第六轮审查发现 `resp.json()` 解析空体必抛 SyntaxError，此前被 logout 的 catch 掩盖）。

## 七、面试追问预案（6 连）

1. **为什么趋势图不直接 SQL 按周聚合？** 跨方言 date_trunc 不通用 + 数据量小，Python 对齐更可测；说得出这个取舍的代价（边缘事件近似）更显真实；
2. **热力图颜色谁定？** 后端只给 done/total，rate 与色阶在前端算——数据与表现分离；
3. **统计口径怎么保证和今日列表一致？** 共享 `COUNTED_PLAN_STATUSES` 单一事实源（domain/constants.py），改口径只改一处；
4. **时段分析的数据从哪来？** completed_at/skipped_at 两个时间戳列（0004 迁移新增 skipped_at），打卡和跳过时由服务端盖戳——用户不能自报时刻，防作弊；
5. **登出后 token 还能用吗？** refresh 立即失效；access 最多残留 15 分钟（短时效就是为此设计的缓解）；
6. **统计接口会被大数据量拖垮吗？** 当前量级（百行）毫秒级；上量后路径：date 列已有索引、可加物化日汇总表——但"先测后优化"，现在加是过度设计。
