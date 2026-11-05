# -*- coding: utf-8 -*-
"""
JPS Refine Studio - FastAPI メインアプリケーション
"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    workspaces_router,
    jobs_router,
    records_router,
    rules_router,
    fetch_router,
    llm_router,
    ndc_router
)
from .config import PROJECT_ROOT

app = FastAPI(
    title="JPS Refine Studio API",
    description="ジャパンサーチ主題特化型メタデータサブセット構築支援システム API",
    version="2.0.0"
)

# CORSミドルウェア設定 (Viteフロントエンド開発サーバー等を許可)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(workspaces_router)
app.include_router(jobs_router)
app.include_router(records_router)
app.include_router(rules_router)
app.include_router(fetch_router)
app.include_router(llm_router)
app.include_router(ndc_router)


@app.get("/api/health")
def health_check():
    """API稼働ヘルスチェック"""
    return {
        "status": "ok",
        "service": "JPS Refine Studio",
        "version": "2.0.0"
    }


# フロントエンドビルド成果物 (frontend/dist) が存在する場合は静的ファイル配信
dist_dir = PROJECT_ROOT / "frontend" / "dist"
if dist_dir.exists() and (dist_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

