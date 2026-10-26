# -*- coding: utf-8 -*-
"""
JS-Refine Studio - 人文学文化資源メタデータ抽出・構造化システム
メインエントリーポイント ＆ ルーティング
"""

import os
import re
import streamlit as st

# コンポーネント ＆ スタイル
from components.styles import inject_custom_css
from components.file_utils import count_lines

# ビューモジュール
from views.dashboard_view import render_dashboard_view
from views.step1_fetch_view import render_step1_view
from views.step2_type_view import render_step2_type_view
from views.step2a_about_view import render_step2a_view
from views.step2b_ngram_view import render_step2b_view
from views.step2c_llm_view import render_step2c_view
from views.step2d_review_view import render_step2d_view
from views.step3_export_view import render_step3_view
from views.workspace_view import render_workspace_view
from modules.workspace_manager import WorkspaceManager

# Streamlit ページ初期化
st.set_page_config(layout="wide", page_title="JS-Refine Studio | メタデータ精緻化システム", page_icon="📚")

# 全体CSSの注入
inject_custom_css()

# パス定数定義（実行元カレントディレクトリに依存せず、絶対パスとして確実に解決）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 01_cleansing_studio
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

# ワークスペースマネージャーの初期化
wm = WorkspaceManager(project_root=PROJECT_ROOT)
workspaces = wm.list_workspaces()
ws_ids = [w["id"] for w in workspaces]
ws_name_map = {w["id"]: w["name"] for w in workspaces}

# サイドバーヘッダー
st.sidebar.title("JS-Refine Studio")
st.sidebar.caption("人文学文化資源 メタデータ精緻化システム")

# ワークスペースが未作成（0件）の場合の特別ローンチハンドリング
if not workspaces:
    st.sidebar.markdown("---")
    st.sidebar.info("💡 **研究プロジェクトが未作成です**\n\n右側の画面から新規プロジェクトを立ち上げてください。")
    # 空のパス辞書でプロジェクト立ち上げビューを直接描画
    render_workspace_view({}, wm)
    st.stop()

# ワークスペース切替セレクタ
if "active_workspace_id" not in st.session_state or st.session_state["active_workspace_id"] not in ws_ids:
    st.session_state["active_workspace_id"] = ws_ids[0]

current_ws_idx = ws_ids.index(st.session_state["active_workspace_id"]) if st.session_state["active_workspace_id"] in ws_ids else 0

selected_ws_id = st.sidebar.selectbox(
    "📁 研究プロジェクト (ワークスペース):",
    options=ws_ids,
    index=current_ws_idx,
    format_func=lambda x: f"📁 {ws_name_map.get(x, x)}",
    key="sb_workspace_select"
)

if selected_ws_id != st.session_state["active_workspace_id"]:
    st.session_state["active_workspace_id"] = selected_ws_id
    st.rerun()

# 選択中ワークスペースのパス辞書を動的生成
PATHS = wm.get_workspace_paths(st.session_state["active_workspace_id"])

def check_status(path):
    return "●" if os.path.exists(path) and os.path.getsize(path) > 0 else "○"

status_map = {
    "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得": PATHS["PATH_RAW_METADATA"],
    "Step 2-A: データ種別 (rdf:type) 分析・除外": PATHS["PATH_TYPE_FILTERED"],
    "Step 2-B: 主題 (schema:about) キーワード分析・判別": PATHS["PATH_ABOUT_FILTERED"],
    "Step 2-C: タイトル語彙・文字列パターン分析・除外": PATHS["PATH_NGRAM_FILTERED"],
    "Step 3: LLMセマンティック適合判定 (判定保留群の分類)": PATHS["PATH_LLM_JUDGMENTS"],
    "Step 4: 専門家による最終査読・手動オーバーライド": PATHS["PATH_VERIFIED_JSONL"],
    "Step 5: データエクスポート (統合検索ポータル出力)": PATHS["PATH_EXPORT_JSON"]
}

menu_options = [
    "📁 プロジェクト・履歴マネージャー",
    "Dashboard",
    "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得",
    "Step 2-A: データ種別 (rdf:type) 分析・除外",
    "Step 2-B: 主題 (schema:about) キーワード分析・判別",
    "Step 2-C: タイトル語彙・文字列パターン分析・除外",
    "Step 3: LLMセマンティック適合判定 (判定保留群の分類)",
    "Step 4: 専門家による最終査読・手動オーバーライド",
    "Step 5: データエクスポート (統合検索ポータル出力)"
]

def format_menu_label(opt):
    if opt == "📁 プロジェクト・履歴マネージャー":
        return "📁 プロジェクト・履歴マネージャー"
    if opt == "Dashboard":
        return "📊 Dashboard"
    p = status_map.get(opt)
    st_mark = check_status(p) if p else "○"
    return f"{st_mark} {opt}"

if "main_menu_choice" not in st.session_state or st.session_state["main_menu_choice"] not in menu_options:
    st.session_state["main_menu_choice"] = "📁 プロジェクト・履歴マネージャー"

choice = st.sidebar.radio("工程を選択:", menu_options, format_func=format_menu_label, key="main_menu_choice")

# メインビュー描画（トップレベル直接ルーティング）
if choice == "📁 プロジェクト・履歴マネージャー":
    render_workspace_view(PATHS, wm)
elif choice == "Dashboard":
    render_dashboard_view(PATHS)
elif choice == "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得":
    render_step1_view(PATHS)
elif choice == "Step 2-A: データ種別 (rdf:type) 分析・除外":
    render_step2_type_view(PATHS)
elif choice == "Step 2-B: 主題 (schema:about) キーワード分析・判別":
    render_step2a_view(PATHS)
elif choice == "Step 2-C: タイトル語彙・文字列パターン分析・除外":
    render_step2b_view(PATHS)
elif choice == "Step 3: LLMセマンティック適合判定 (判定保留群の分類)":
    render_step2c_view(PATHS)
elif choice == "Step 4: 専門家による最終査読・手動オーバーライド":
    render_step2d_view(PATHS)
elif choice == "Step 5: データエクスポート (統合検索ポータル出力)":
    render_step3_view(PATHS)

