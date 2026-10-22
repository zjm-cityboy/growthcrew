# 服务器部署手册（服务器 + 域名 + HTTPS 模式）

> 目标：在一台装有 Docker 的 Linux 服务器上，把 GrowthCrew 跑起来并可通过 HTTPS 访问。
> 本文件使用 `docker-compose.server.yml`（db + backend + Caddy 自动 HTTPS，仅后端 API，
> 前端需另行托管或用本模式反代）。**本机 Docker Desktop 部署请用根目录 DEPLOY.md
> （`docker-compose.yml` + setup.bat 一键脚本）。**

## 前置条件

- 一台 Linux 服务器（已装 Docker 与 docker compose 插件）
- 一个已解析到该服务器的域名（用于自动 HTTPS）
- 本地仓库已推送（`git push origin main`）

## 步骤

```bash
# 1. 服务器上拉代码
git clone https://github.com/<你的用户名>/growthcrew.git
cd growthcrew/deploy

# 2. 准备环境变量（绝不提交 .env）
cp .env.example .env
vim .env   # 填 DOMAIN / GC_JWT_SECRET / POSTGRES_PASSWORD

# 3. 生成随机密钥的快捷方式（本地或服务器任一有 Python 的机器）
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. 启动全部服务（db 健康后 backend 自动起，Caddy 自动签证书）
docker compose -f docker-compose.server.yml up -d --build

# 5. 执行数据库迁移
docker compose -f docker-compose.server.yml exec backend alembic upgrade head

# 6. 验证
curl https://<你的域名>/api/v1/health/live    # {"status":"ok",...}
curl https://<你的域名>/api/v1/health/ready   # database: up
```

## 日常运维

```bash
# 看日志
docker compose -f docker-compose.server.yml logs -f backend

# 升级（拉新代码后）
git pull && docker compose -f docker-compose.server.yml up -d --build && docker compose -f docker-compose.server.yml exec backend alembic upgrade head

# 备份（建议加入 crontab，每天一次；用户名/库名从容器环境变量取，不硬编码）
docker compose -f docker-compose.server.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > backup_$(date +%F).sql.gz
```

## 安全清单（部署后自查）

- [ ] `https://域名/api/v1/health/live` 返回 200，且 http 自动跳 https
- [ ] `.env` 未出现在 `git status` 中
- [ ] 服务器防火墙只开放 22/80/443
- [ ] 备份 crontab 已配置并验证可恢复（异地留存一份）
- [ ] 限速拿到真实 IP：不同设备连续错误登录 11 次，应各自收到 429（若过早 429，说明 FORWARDED_ALLOW_IPS 未生效，检查 compose 网络 IP 是否一致）
