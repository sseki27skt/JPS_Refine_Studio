# -*- coding: utf-8 -*-
"""
JPS Refine Studio バックエンド起動エントリーポイント
"""
import uvicorn
import os
import sys

# 親ディレクトリを sys.path に追加
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if __name__ == "__main__":
    host = os.getenv("JPS_HOST", "127.0.0.1")
    port = int(os.getenv("JPS_PORT", "8000"))
    reload = os.getenv("JPS_RELOAD", "True").lower() in ("true", "1", "yes")

    print(f"Starting JPS Refine Studio API Server on http://{host}:{port} (reload={reload})...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)

