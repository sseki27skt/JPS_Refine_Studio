# -*- coding: utf-8 -*-
"""
JPS Refine Studio - システム共通パス・環境変数設定
"""
import os
from pathlib import Path

# backend/app/config.py -> backend/app -> backend -> PROJECT_ROOT
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# データパス
DATA_DIR = PROJECT_ROOT / "data"
WORKSPACES_DIR = DATA_DIR / "workspaces"
DEFAULT_RULES_DIR = PROJECT_ROOT / "01_cleansing_studio" / "rules"
VIEWER_DIR = PROJECT_ROOT / "02_search_viewer"

# キャッシュパス
CACHE_DIR = DATA_DIR
NDC_CACHE_FILE = CACHE_DIR / "ndc_api_cache.json"
NDLNA_CACHE_FILE = CACHE_DIR / "ndlna_api_cache.json"
NDLC_CACHE_FILE = CACHE_DIR / "ndlc_api_cache.json"

# サーバー設定
DEFAULT_HOST = os.getenv("JPS_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("JPS_PORT", "8000"))
DEBUG = os.getenv("JPS_DEBUG", "True").lower() in ("true", "1", "yes")

# ディレクトリ存在確保
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

