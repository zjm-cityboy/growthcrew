# GrowthCrew 部署指南（本地 Docker 版）

> 拿到项目压缩包之后，在一台装了 **Docker Desktop** 的电脑上，从零到能打开网页使用，
> 只需要一步：**双击 `deploy/setup.bat`**。本文档覆盖一键部署、手动部署、首次使用、
> 常见问题和完全卸载。所有路径均为相对路径，压缩包解压到任意盘符任意目录都可以。

---

## 1. 部署后是什么形态

| 容器 | 说明 | 宿主机端口 |
|------|------|-----------|
| frontend | Next.js 网页（手机优先 PWA） | **3211** → http://localhost:3211 |
| backend | FastAPI（3 个 LLM Agent + API） | 8100（一般不需要直接访问） |
| db | PostgreSQL 16（数据都存在它的 Docker 卷里） | 不对宿主机暴露 |

浏览器访问 `http://localhost:3211`，网页自己会调 `http://127.0.0.1:8100` 的 API，
同机部署零配置。

## 2. 你需要准备什么

- **Docker Desktop** 4.x 及以上（Windows / macOS 均可；Linux 用 docker engine + compose 插件）
  - 未安装：https://www.docker.com/products/docker-desktop/ 下载安装后启动它
  - 验证可用：终端执行 `docker info` 有输出即可
- 约 2 GB 磁盘空间（镜像 + 数据）
- **不需要** Python、Node.js、git——全部在容器里

## 3. 一键部署（推荐）

**Windows：双击 `deploy/setup.bat`**

**macOS / Linux：**

```bash
cd deploy
chmod +x setup.sh && ./setup.sh
```

脚本会自动完成（每步都有输出，出错会停并告诉你怎么看日志）：

1. 检查 Docker 正在运行
2. 生成三个随机密钥，写入 `deploy/.env`（已存在则沿用，不会覆盖）
3. `docker compose up -d --build` 构建并启动三个容器（**首次约 3-10 分钟**，
   要下载基础镜像和依赖）
4. 轮询后端健康检查，直到数据库迁移完成、服务就绪

看到这样的输出就是成功：

```
[4/4] All services are up.
  App (open in browser):   http://localhost:3211
```

浏览器打开 **http://localhost:3211** 即可。

## 4. 手动部署（不想跑脚本）

```bash
# 1. 进入 deploy 目录（下文所有命令都在这里执行）
cd deploy

# 2. 复制环境变量模板
cp .env.example .env        # Windows: copy .env.example .env

# 3. 生成三个随机值，填进 .env 对应位置（已装 python 的话）
python -c "import secrets; print(secrets.token_urlsafe(48))"        # -> GC_JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"        # -> GC_ENCRYPTION_KEY（44 位即正确）
python -c "import secrets; print(secrets.token_hex(12))"            # -> POSTGRES_PASSWORD

#    没有 python 用 openssl：
#    openssl rand -base64 48 | tr '+/' '-_' | tr -d '='

# 4. 构建并启动
docker compose up -d --build

# 5. 验证（backend 首次启动会自动跑数据库迁移，等 10-30 秒）
curl http://localhost:8100/api/v1/health/ready
# 期望输出包含 {"status":"ok","database":"up"}
```

## 5. 首次使用（应用内三步）

1. **注册**：打开 http://localhost:3211 → 注册 → 用户名 ≥3 位、密码 ≥8 位
2. **配模型密钥**：设置页 → 模型配置 → 选「硅基流动」→ 粘贴 API 密钥 → 保存并验证。
   密钥去 https://siliconflow.cn 免费注册领取（约 1 分钟）；也可以用任何
   OpenAI 兼容服务（DeepSeek 官方 / 自建网关），选「其他 / 自定义」填 URL 和模型名。
   密钥用 Fernet 加密后才落库，服务端不留明文。
3. **生成第一份计划**：对话页 → 新建目标 → 贴一段学习计划（或写一句话）→
   「生成我的周计划」→ 看着 AI 时间线跑完 → 点「同意」，任务就出现在今日页。

> 不配模型密钥也能用打卡和统计功能，但 AI 排计划 / 周报不可用。

## 6. 日常运维

```bash
cd deploy            # 以下命令都在 deploy 目录执行

docker compose ps            # 看三个容器状态（应均为 running/healthy）
docker compose logs -f backend    # 看后端日志（排错第一现场）
docker compose down          # 停止（数据保留）
docker compose up -d         # 再次启动（不用 --build，秒起）
docker compose down -v       # ⚠️ 停止并删除全部数据（账号/打卡记录全没）
```

**数据备份**（建议定期做）：

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup_$(date +%F).sql
```

**数据恢复**：

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < backup_2026-10-01.sql
```

数据实际存放位置：Docker 卷 `growthcrew_local_pgdata`（由 Docker Desktop 统一管理，
与本项目目录无关，删项目文件夹不会删数据）。

## 7. 常见问题

**Q1：启动报「ports are not available / access permissions」**

Windows 特有的坑：Hyper-V/WSL 会随机圈占一段端口（每台电脑不同，重启还会变），
被圈中的端口连 Docker 都绑不上。本包默认的 3211/8100 已尽量避开常见段，
但仍有小概率撞上。两条路任选：

```bash
# 先看你机器圈了哪些段（管理员 PowerShell / CMD）
netsh interface ipv4 show excludedportrange protocol=tcp
```

- **换端口（简单）**：改 `deploy/docker-compose.yml` 里 `ports` 冒号**左边**的数字
  （选一个不在排除段里的），前端端口还要同步改 `.env` 的 `GC_CORS_ORIGINS`，
  然后 `docker compose up -d`（后端端口变了则需重建前端镜像，见 Q2）
- **根治（管理员，一劳永逸）**：
  `netsh int ipv4 set dynamicport tcp start=49152 num=16384` 后重启电脑

**Q2：3211 或 8100 端口被别的程序占了 / 我想换端口**

改 `deploy/docker-compose.yml` 里两处 `ports` 映射冒号左边的宿主端口：

```yaml
  backend:
    ports:
      - "8100:8000"     # 改成 8200:8000 之类
  frontend:
    ports:
      - "3211:3000"
```

注意耦合关系：
- 改 **3211**（前端）：还要同步改 `.env` 里 `GC_CORS_ORIGINS` 的端口号，然后
  `docker compose up -d` 重启后端
- 改 **8100**（后端）：前端的 API 地址是构建时写死的默认值 `http://127.0.0.1:8100/api/v1`，
  必须带着新地址重新构建前端镜像：
  `docker compose build --build-arg NEXT_PUBLIC_API_URL=http://127.0.0.1:8200/api/v1 frontend`
  然后 `docker compose up -d`

**Q3：改过 `.env` 里的 `POSTGRES_PASSWORD` 后，backend 起不来（password authentication failed）**

PostgreSQL 只在**第一次创建数据卷时**用当时的密码初始化，之后改 `.env` 里的密码
不会同步进数据库，只会让后端连不上。两种解法：

- 数据不重要：`docker compose down -v` 删卷重来（⚠️ 全部数据清零），再 `docker compose up -d`
- 想保数据：把 `.env` 里的密码改回创建时的那个值

同理 `GC_ENCRYPTION_KEY` 换新后，用户已保存的模型密钥会解不开，需要在应用设置页
重新录入（账号数据不受影响）。

**Q4：怎么给自己管理员权限（管理后台）？**

先在应用里注册好你的账号（比如 `admin`），然后编辑 `deploy/.env`：

```
GC_ADMIN_USERNAMES=["admin"]
```

再 `docker compose up -d`（重启 backend 生效）。浏览器打开
http://localhost:3211/admin 进入管理后台（用户端界面上没有入口，属有意设计）。
**顺序必须是先注册后配置**，否则别人抢先注册同名账号就会拿到管理员。

**Q5：setup.bat 双击闪退 / 报 Docker 错误**

先确认 Docker Desktop 已经完全启动（右下角鲸鱼图标稳定不再转）。然后在
`deploy` 目录开个终端手动跑 `powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1`
看完整输出。

**Q6：后端起来了但页面调 API 报跨域（CORS）错误**

检查访问地址和 `.env` 的 `GC_CORS_ORIGINS` 是否一致：用 `http://localhost:3211`
访问就需要白名单里有 `http://localhost:3211`；用 `127.0.0.1` 访问同理。改完
`docker compose up -d` 重启。

**Q7：想彻底删除**

```bash
cd deploy && docker compose down -v      # 停容器+删数据卷
docker rmi growthcrew-backend growthcrew-frontend postgres:16-alpine   # 删镜像
```

## 8. 另一种部署模式：服务器 + 域名 + HTTPS

本包默认是**本机部署**（localhost，无 HTTPS）。如果要部署到公网服务器并绑定域名
（Caddy 自动签发证书），使用 `deploy/docker-compose.server.yml`，步骤见
`deploy/runbook.md`。

## 9. 本文档的验证记录

以下步骤在 Windows 10 + Docker Desktop（Docker Engine 29.7.2）实测通过（2026-10-01）：

- [x] 一键脚本（setup.bat → setup.ps1）从零跑通：自动生成密钥 → 三容器全部 healthy
- [x] 首次启动自动迁移（alembic），`/health/ready` 返回 `database: up`
- [x] API 注册 → 登录 → 带 token 访问均正常
- [x] 浏览器打开 http://localhost:3211 → 登录 → 今日页完整渲染
- [x] `docker compose down` → `up -d` 重启后账号数据仍在
- [x] 压缩包解压到完全不同的路径（C 盘临时目录）部署成功，无绝对路径依赖
- [x] 验证中发现并修复的坑：PS 5.1 兼容性×2、Fernet 密钥 padding、
      Windows 保留端口段（3100→3211）、改 PG 密码与旧数据卷冲突（见 FAQ Q3）
