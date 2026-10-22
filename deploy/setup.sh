#!/usr/bin/env bash
# GrowthCrew one-click local deployment (macOS / Linux, or Git Bash on Windows)
# What it does: check docker -> generate secrets -> write .env -> compose up --build
#               -> wait for backend health -> print access URLs
# No absolute paths anywhere; everything is relative to this script's folder.
set -euo pipefail
cd "$(dirname "$0")"

echo "== GrowthCrew local deployment =="

# 1. docker available?
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker is not running. Start Docker Desktop first, then re-run ./setup.sh"
    exit 1
fi

# 2. .env (keep existing one so secrets/data survive re-runs)
if [ -f .env ]; then
    echo "[1/4] .env already exists - keeping it (delete it to regenerate secrets)"
else
    echo "[1/4] Generating .env with fresh random secrets ..."
    # keep base64 padding ('='): Fernet keys must be 44 chars WITH the trailing '='
    JWT=$(openssl rand -base64 48 | tr '+/' '-_' | tr -d '\n')
    FKEY=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')   # 44-char urlsafe = valid Fernet key
    PGPWD=$(openssl rand -hex 12)
    cat > .env <<EOF
GC_ENV=prod
GC_JWT_SECRET=${JWT}
GC_ENCRYPTION_KEY=${FKEY}
GC_CORS_ORIGINS=["http://localhost:3211","http://127.0.0.1:3211"]
GC_ADMIN_USERNAMES=[]
POSTGRES_USER=growthcrew
POSTGRES_PASSWORD=${PGPWD}
POSTGRES_DB=growthcrew
EOF
    echo "      .env written (never commit or zip it)"
fi

# 3. build & start (db -> backend auto-migrates -> frontend)
echo "[2/4] Building images and starting containers (first run takes a few minutes) ..."
docker compose up -d --build

# 4. wait for backend readiness (migration runs on first boot)
echo "[3/4] Waiting for backend (first boot runs DB migrations) ..."
ready=0
for i in $(seq 1 60); do
    if curl -sf -o /dev/null --max-time 3 http://localhost:8100/api/v1/health/ready; then
        ready=1
        break
    fi
    sleep 4
done
if [ "$ready" -ne 1 ]; then
    echo "[ERROR] Backend not ready after 4 min. Check: docker compose logs backend"
    exit 1
fi

echo "[4/4] All services are up."
echo ""
echo "  App (open in browser):   http://localhost:3211"
echo "  Backend health:          http://localhost:8100/api/v1/health/ready"
echo ""
echo "  First time: register an account in the app, then set your model"
echo "  (LLM) API key in Settings. See DEPLOY.md for details."
echo ""
echo "  Stop:  docker compose down      (data kept in docker volume)"
echo "  Start again: docker compose up -d"
echo "  Full reset:  docker compose down -v   (DELETES all data)"
