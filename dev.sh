#!/bin/bash
# ==============================================================================
# JPS Refine Studio v2.0 - 開発サーバー一発起動スクリプト (Backend + Frontend HMR)
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo "  🚀 JPS Refine Studio v2.0 開発サーバーを起動します"
echo "  - FastAPI (Backend): http://127.0.0.1:8000 (API Docs: /docs)"
echo "  - React SPA (Vite):  http://localhost:5173 (ホットリロード対応)"
echo "=========================================================="

# 仮想環境のアクティベート
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# 終了時のクリーンアップ
cleanup() {
    echo ""
    echo "🛑 サーバーを停止しています..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# 1. バックエンド起動
echo "▶ バックエンド (FastAPI) を起動中..."
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# 2. フロントエンド起動
echo "▶ フロントエンド (Vite Dev Server) を起動中..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

wait

