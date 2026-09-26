# 03 · 工程规范与踩坑实录

> 比喻：规范是交规，踩坑是事故报告——每条坑按"现象→根因→修法→面试一句话"记录，10 条全部实测发生。

## 一、工程规范（一页读完）

- **分层铁律**：`api → service → repository` 单向依赖；业务规则只在 service；SQL 只在 repository；**Agent 工具与前端按钮走同一条 service/repo 写入路径**（两条路 = 两套权限两套测试，必出事）；
- **CI 四关**：ruff lint / ruff format / mypy strict / pytest（覆盖率≥80%），外加 SQLite+PG16 **双库跑** 和**迁移冒烟**（up→down→up 真执行）；
- **提交纪律**：Conventional Commits；我暂存、用户 commit+push（Mimosa 分工沿袭）；
- **审查文化**：每里程碑自动跑一轮无偏 code-reviewer（子代理不带辩护词、只给中性规格），5 轮共 44 项发现全部当轮修复——这在面试里是"代码质量如何保证"的标准答案。

## 二、踩坑实录（按发现轮次）

### 坑 1：alembic.ini 里的中文注释让迁移崩溃（P0）
- **现象**：`alembic upgrade` 报 `UnicodeDecodeError: 'gbk' codec can't decode`；
- **根因**：Windows 的 logging.config 用系统默认 GBK 编码读 ini，UTF-8 中文注释直接炸；
- **修法**：alembic.ini 全 ASCII 并注释说明；迁移脚本本体（.py）不受影响（Python 显式 UTF-8）。

### 坑 2：字段名 date 遮蔽类型 date（P1.1）
- **现象**：Pydantic 模型里 `date: date | None = None` 抛 `TypeError: NoneType | NoneType`；
- **根因**：类体内字段名 `date` 遮蔽了 `datetime.date` 类型名，注解求值时 `date` 已是 None；
- **修法**：`from datetime import date as _date` + 注解写字符串 `"_date | None"`（schemas/life·task·today 三处）。

### 坑 3：异步惰性加载 MissingGreenlet（P1.1）
- **现象**：序列化 `goal.milestones` 抛 `MissingGreenlet: greenlet_spawn has not been called`；
- **根因**：SQLAlchemy async 禁止隐式同步 IO，序列化时触发 relationship 惰性加载；
- **修法**：relationship 加 `lazy="selectin"` 预加载（查询时一次带出）。

### 坑 4：fastmcp 工具函数名遮蔽导入的算法函数（P1.2）
- **现象**：mypy 报"Coroutine 没有 capacity_minutes 属性"；
- **根因**：`@mcp.tool` 装饰的 `schedule_week` 与导入的算法函数**同名**，函数体内调用解析到装饰后的包装器；
- **修法**：`from ... import schedule_week as run_scheduler`；教训：**装饰器会改变名字绑定，命名先查导入区**。

### 坑 5：openai 默认 600 秒超时拖死整条链（P1.2 审查）
- **现象风险**：Agent 单请求串行多次 LLM 调用，供应商故障时请求+DB 连接挂 10-30 分钟；
- **修法**：`AsyncOpenAI(timeout=30, max_retries=1)` + API 层把 openai 异常映射 502。

### 坑 6：后台启动 uvicorn 的 cwd 漂移（P1.4 E2E）
- **现象**：注册 500，日志 `no such table: users`——迁移明明跑过；
- **根因**：后台命令的工作目录被重置，SQLite 相对路径 `./growthcrew.db` 指向了另一个目录（空库）；
- **修法**：启动前显式 `cd backend`；教训：**相对路径配置对 cwd 敏感，服务启动目录要进 runbook**。

### 坑 7：SQLite 与 PG 的 timestamptz 比较口径（P1.5 审查）
- **现象风险**：通知去重按 `created_at >= 今天北京 0 点`，SQLite 存朴素 UTC 串、PG 存 timestamptz，直接比较两种库行为不一致（07:00 北京 = 前一天 23:00 UTC，日期还会错位）；
- **修法**：`cn_day_start_utc_naive()`——北京 0 点转**朴素 UTC** 再比较，两种引擎语义一致；
- **面试一句话**：跨库时间比较要么全 aware 要么全朴素 UTC，混用必错位。

### 坑 8：迁移枚举列缺 length（P1.1 审查）
- **现象**：ORM 声明 VARCHAR(20)，迁移实际建出 VARCHAR(2~7)（SQLAlchemy 对非原生枚举默认取最长值）；
- **危害**：未来加长枚举值 → PG 写入报错，SQLite 测不出来（不强制长度）；
- **修法**：迁移统一 `length=20`，并在真 PG 上 `information_schema` 抽查实证。

### 坑 9：upsert 的 check-then-write 竞态（P1.1 审查）
- **现象风险**：双击保存 → 两个请求都查到 None → 都 INSERT → 撞唯一约束 500；
- **修法范式**（全仓通用）：`except IntegrityError: rollback → 重新 get → 走更新分支`（注册/生活打卡/复盘/计划版本四处同款）。

### 坑 10：ruff 对中文项目与 FastAPI 的误报（P0）
- **RUF001-003**（全角标点"ambiguous"）与 **B008**（`Depends()` 写参数默认值是 FastAPI 惯用法）→ 配置里**带理由** ignore，不是无脑全关。

## 三、双库测试为什么值得（面试高频）

SQLite 快但方言宽容（不查长度、时间朴素存储），PG 才是生产方言——**只用 SQLite 的全绿是虚假信心**（坑 7/8 都只有 PG 能暴露）。CI 两个 job 同一套 53 用例各跑一遍，PG 由 service 容器提供，测试夹具按 `GC_TEST_DB_URL` 切库并先 drop 再 create。
