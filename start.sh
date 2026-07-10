#!/usr/bin/env bash
# 一鍵啟動 DocuMind：檢查 5432 port 沒被 WSL 內建 PostgreSQL 占用後，
# 依序拉起 docker-compose postgres、後端 (FastAPI)、前端 (Vite)。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PORT=5432

port_is_open() {
    (echo > "/dev/tcp/127.0.0.1/${PORT}") >/dev/null 2>&1
}

our_postgres_running() {
    docker compose ps --status running --services 2>/dev/null | grep -qx postgres
}

if port_is_open; then
    if our_postgres_running; then
        echo "✅ PostgreSQL（docker-compose）已在 ${PORT} 執行中，跳過啟動。"
    else
        echo "❌ Port ${PORT} 已被占用，但不是本專案的 docker-compose postgres。"
        echo "   最常見原因：WSL 內建的 PostgreSQL 服務正在跑，跟 docker 容器搶 port。"
        echo "   請先關閉它，再重新執行這個腳本："
        echo "     sudo service postgresql stop"
        echo "   或用 'sudo lsof -i:${PORT}' 找出實際占用的程序。"
        exit 1
    fi
else
    echo "⏳ 啟動 PostgreSQL（docker compose）..."
    docker compose up -d
fi

echo "⏳ 啟動後端 (FastAPI)..."
uv run uvicorn main:app --reload &
BACKEND_PID=$!

echo "⏳ 啟動前端 (Vite)..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap 'echo "🛑 關閉服務中..."; kill "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null' EXIT INT TERM

wait
