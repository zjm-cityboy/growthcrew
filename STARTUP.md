# GrowthCrew 成长小队 · 启动指南

> 从开机到可用，两条路：**日常启动**（30 秒）和**首次部署**（约 10 分钟）。

---

## 一、日常启动（已经部署过，开机就能用）

### 你需要开两个终端

**终端 1 —— 后端 API（端口 8000）**

```bash
cd D:\growthcrew\backend
D:\anaconda3\envs\growthcrew\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**终端 2 —— 前端页面（端口 3000）**

```bash
cd D:\growthcrew\frontend
npm run dev
```

**打开应用**

手机或电脑浏览器访问 → `http://localhost:3000`

> 💡 手机测试：把 `localhost` 换成你电脑的局域网 IP（`ipconfig` 查看），如 `http://192.168.1.100:3000`

### 停止

两个终端各按 `Ctrl + C` 即可。

---

## 二、首次部署（从零开始，约 10 分钟）

### 前提：已安装的软件

| 软件 | 用途 | 你的安装位置 |
|---|---|---|
| Anaconda | Python 环境 | `D:\anaconda3` |
| Node.js ≥ 20 | 前端构建 | 已在 PATH |
| Git | 版本控制 | 已在 PATH |

### 步骤 1：创建 Python 环境（首次）

```bash
conda create -n growthcrew python=3.12 -y
conda activate growthcrew
cd D:\growthcrew\backend
pip install -e ".[dev,agents,jobs]"
```

### 步骤 2：建数据库表（首次或表结构变更后）

```bash
cd D:\growthcrew\backend
D:\anaconda3\envs\growthcrew\python.exe -m alembic upgrade head
```

> 看到最后一条 `Running upgrade ...` 无报错即成功。本地默认用 SQLite（`backend/growthcrew.db`），无需额外安装数据库。

### 步骤 3：启动

回到"日常启动"那两条命令。

### 步骤 4：注册 + 配置

1. 打开 `http://localhost:3000` → 点"注册" → 输入用户名密码
2. 点底部"档案"Tab → "模型与推送设置 →"
3. **BYOK 三件套**：
   - Base URL：`https://api.siliconflow.cn/v1`（硅基流动）
   - API Key：你的 `sk-` 开头密钥
   - 模型名：如 `Qwen/Qwen3.5-35B` 或 `deepseek-ai/DeepSeek-V4-Flash`
4. （可选）推送通道：选 Bark/PushPlus/企微 → 粘贴端点 URL → "保存并发测试"

### 步骤 5：开始使用

1. **对话**Tab → 选/新建目标 → 贴入参考计划文本 → "开始对齐"
2. 等十几秒 → 教练出提案 → 点"同意"
3. **今日**Tab → 看到任务了 → 点圆圈打卡 / 跳过选卡因
4. 晚上 21:30 → 收到提醒 → 写一分钟复盘
5. 周日晚 → 复盘师自动生成周报

---

## 三、一键启动脚本（推荐）

把以下内容存为 `D:\growthcrew\start.bat`，以后双击即可：

```bat
@echo off
title GrowthCrew Backend
start "GrowthCrew Frontend" cmd /k "cd /d D:\growthcrew\frontend && npm run dev"
cd /d D:\growthcrew\backend
D:\anaconda3\envs\growthcrew\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 四、生产部署（服务器）

详见 `deploy/runbook.md`。核心差异：
- 用 PostgreSQL 替代 SQLite（compose 文件已配好）
- 用 Docker Compose 一键起全套（数据库 + 后端 + Caddy HTTPS）
- 需要 `.env` 文件配置域名/密钥

---

## 五、常见问题

| 问题 | 解法 |
|---|---|
| 后端启动报 `no such table` | 忘了跑迁移 → `alembic upgrade head` |
| 前端页面白屏 | 后端没启动 → 先开终端 1 |
| 对话页"开始对齐"报错 | BYOK 未配置或密钥无效 → 检查设置页 |
| 手机打不开 | 用局域网 IP 替代 localhost；防火墙放行 3000 端口 |
| 想重置全部数据 | 删除 `backend/growthcrew.db` → 重跑 `alembic upgrade head` |

---

## 六、验证一切正常

启动后打开 `http://127.0.0.1:8000/api/v1/health/ready`

应返回：`{"status":"ok","version":"0.1.0","database":"up"}`
