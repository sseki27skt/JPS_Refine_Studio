#!/bin/bash
# ==============================================================================
# JPS Refine Studio v2.0 - 単一ポート統合起動スクリプト (http://localhost:8000)
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo "  🚀 JPS Refine Studio v2.0 (統合モード)"
echo "  - Web UI: http://127.0.0.1:8000"
echo "  - API Docs: http://127.0.0.1:8000/docs"
echo "=========================================================="

if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# フロントエンドがビルド済みでない場合はビルド
if [ ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
    echo "▶ フロントエンドをビルドしています..."
    (cd "$PROJECT_ROOT/frontend" && npm run build)
fi

echo "▶ 統合サーバーを起動中..."
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

