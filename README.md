# GrowthCrew · 成长小队

> 面向自学者的多智能体成长执行系统 — 贴入你的计划，AI 排进每天并盯着你执行。

[![CI](https://github.com/zjm-cityboy/growthcrew/actions/workflows/ci.yml/badge.svg)](https://github.com/zjm-cityboy/growthcrew/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

## 它做什么

| 功能 | 说明 |
|---|---|
| **计划导入对齐** | 贴入经验帖/课表，或写一句话（"我要3个月拿下软考"），教练 Agent 自动拆解科目、排程到每天（每日 ≤3 件） |
| **每日执行** | 晨间摘要推送、一键打卡（≤2 步）、跳过时选卡因（分心/太难/疲劳/被打断）、生活三打卡 |
| **周报洞察** | 复盘师 Agent 每周自动钻取数据（完成率→卡因分布→时段模式），生成"你 22 点后的任务全跳过了"级别的洞察 |
| **HITL 审批** | 计划改动必须人工审批才生效（服务层条件 UPDATE 原子操作） |
| **错题本** | 录题→LLM 讲解→间隔复习（简化 SM-2：答对翻倍/答错重置/5次掌握），到期混入晨推 |
| **推送通道** | Bark（iOS）/ PushPlus（微信）/ 企微 webhook，三选一 + 一键测试 |
| **数据主权** | BYOK（用户自带 API 密钥，Fernet 加密落库）+ 一键 CSV 全量导出 |
| **离线打卡** | 断网打卡入队 localStorage，联网自动补传（含 token 刷新重试） |

## 架构

```
手机 PWA（今日/对话/档案 三 Tab）
       │ HTTPS
  Caddy 反向代理（自动 HTTPS + 安全头）
       │
  FastAPI 后端
     ├── 教练 Agent ── LangGraph StateGraph（条件边+工具循环）
     ├── 复盘师 Agent ── FastMCP 工具循环（纯线性，无图）
     ├── 陪练 ── 单次 LLM 调用（错题讲解）
     ├── 管家 ── 零 LLM（APScheduler 晨推/提醒）
     └── PostgreSQL（业务数据 + 审计日志）
```

### 三种编排粒度（核心设计决策）

| Agent | 编排方式 | 工具数 | 为什么 |
|---|---|---|---|
| 教练 | LangGraph 图 | 4 | 有条件分支（缺信息提前返回追问） |
| 复盘师 | 工具循环 | 4 | 纯线性但钻取顺序临场定 |
| 陪练 | 单次调用 | 0 | 题目即完整上下文 |

> **设计原则**：只在需要"见机行事"的地方用 Agent，能写死的坚决写死。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic（7 个迁移） |
| Agent | LangGraph 1.2 · FastMCP 4.0 · OpenAI SDK（BYOK 动态 base_url） |
| 数据库 | PostgreSQL 16（生产）· SQLite（开发/测试双跑） |
| 前端 | Next.js 16 · React 19 · TypeScript strict · Tailwind v4 · ECharts（按需加载） |
| PWA | Service Worker · 离线打卡队列 · manifest |
| 定时任务 | APScheduler（4 个 cron：晨推/晚间/周报/周三） |
| 推送 | httpx 适配器（Bark/PushPlus/企微 webhook） |
| 安全 | argon2id · JWT 旋转 · Fernet · SSRF 防护 · Prompt 注入四层防御 |
| 质量 | ruff · mypy strict · pytest 87 用例双库 · 11 轮代码审查 |

## 工程实践

- **CI 四关门禁**：ruff lint+format / mypy strict / pytest（SQLite+PG16 双库，覆盖率 ≥80%）/ pip-audit
- **11 轮无偏代码审查**：每完成一个里程碑自动启动 code-reviewer 审查，75 项发现全部当轮修复（含 3 个 P0）
- **三方独立审查**：PM（25 项 UX 发现）/ 安全工程师（6 项漏洞）/ QA（12 项测试发现），必修+应修 18 项全修
- **7 个 ADR**：每个架构决策记录含"被否方案"和选择理由
- **分层铁律**：api → service → repository 单向依赖，Agent 工具与前端按钮走同一条被测试覆盖的写入路径

## 快速开始

```bash
# 后端
cd backend
pip install -e ".[dev,agents,jobs]"
alembic upgrade head
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev

# 打开 http://localhost:3000
```

详细部署见 [deploy/runbook.md](deploy/runbook.md)

## 项目阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 脚手架 · 认证 · CI/CD · 部署链路 | ✅ |
| P1 | 教练 Agent · 计划导入对齐 · 每日打卡 · 前端三 Tab · 晨推 | ✅ |
| P2 | 复盘师 Agent · 统计四端点 · 推送通道 · 前端图表 | ✅ |
| P3 | 数据导出 · PWA · 离线队列 · 暗色模式 | ✅ |
| P4 | 错题本 · 间隔复习 | ✅ |
| P5 | 专业问答 + 知识库 RAG | 🔜 |

## License

[AGPL-3.0](LICENSE)
