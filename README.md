# GrowthCrew · 成长小队

> 面向懂技术的自学者的成长执行系统：贴入你的备考/求职/健身计划，AI 排进每天并盯着你执行——打卡路径两步、卡因一键记录、每周给"它懂我"级别的复盘洞察和调整提案（你审批才生效）。自托管 + 自带模型密钥（BYOK），成长数据在自己手里。

## 它解决什么问题

计划工具记录"你打算做什么"，GrowthCrew 管理"实际怎么过成这样"：

- **计划导入对齐**：贴入经验帖/机构计划/学长 Excel，教练 Agent 对齐到"里程碑 → 周 → 日"（每日核心任务默认 ≤3 件）
- **每日执行**：晨间摘要推送、一键打卡、跳过时一键选卡因（分心/太难/疲劳/被打断）、生活三打卡（睡眠/运动/心情）
- **周复盘闭环**：复盘师基于完成数据 + 卡因 + 时段模式生成洞察与调整提案，**你审批后才生效**
- **多目标仲裁**：秋招冲刺和健身抢时间时，教练做全局调度

详细设计见 [docs/00-产品调研与技术方案.md](docs/00-产品调研与技术方案.md)。

## 架构一览

```
手机 PWA（今日 / 对话 / 档案，三 Tab）
        │  HTTPS
Caddy 反向代理（自动 HTTPS + 安全头）
        │
FastAPI 后端 ── api → service → repository 三层
   ├── Agent 编排：LangGraph（总编路由 + 教练 + 复盘师；HITL 中断审批）
   ├── 工具层：FastMCP（Agent 只能调 service 层，权限矩阵管控）
   ├── 定时任务：APScheduler（晨推/周三小结/周报，模板渲染零 LLM）
   └── PostgreSQL（业务数据 + Agent checkpoint + 审计日志）
```

设计原则：**只在真正需要"见机行事"的地方用 Agent，能写死的坚决写死。**
Agent 可以修改未来的安排，但不能篡改过去的事实。

## 快速开始（本地开发）

```bash
# 后端（Python 3.12）
conda create -n growthcrew python=3.12 -y
conda activate growthcrew
cd backend
pip install -e ".[dev]"
alembic upgrade head          # 建表（默认本地 SQLite）
uvicorn app.main:app --reload # http://127.0.0.1:8000/api/docs

# 前端（Node ≥ 20）
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

服务器部署见 [deploy/runbook.md](deploy/runbook.md)。

## 工程规范

- **质量门禁**（CI 四关，全绿才可合入）：ruff lint + format / mypy 严格模式 / pytest（覆盖率 ≥80%）/ pip-audit
- **分层铁律**：`api → service → repository` 单向依赖；SQL 只在 repository；业务规则只在 service
- **提交规范**：Conventional Commits（feat / fix / refactor / docs / chore）
- **迁移纪律**：schema 变更只通过 Alembic，禁止手改线上库

## 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 仓库 / 环境 / 认证 / 部署链路 | ✅ 进行中 |
| P1 | 计划导入对齐 → 审批 → 每日打卡闭环 | ⬜ |
| P2 | 复盘师周报 + 洞察 + 推送双通道 + 档案图表 | ⬜ |
| P3 | 加固与试运行（兜底/备份/离线补传，连续 2 周真实使用） | ⬜ |
| P4 | 错题本（录题 → LLM 讲解 → 间隔复习） | ⬜ |
| P5 | 专业问答 + 知识库 RAG（先专项调研） | ⬜ |

## License

[AGPL-3.0](LICENSE)
