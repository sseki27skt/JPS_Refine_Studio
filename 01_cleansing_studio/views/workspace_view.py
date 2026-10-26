# -*- coding: utf-8 -*-
"""
JS-Refine Studio - ワークスペース ＆ フィルタリング履歴マネージャービュー
- 研究テーマ（ワークスペース）の作成・切替・削除
- フィルタリング経過（スナップショット）の保存・復元・タイムライン管理
- 共同研究用パッケージ（ZIP）のエクスポート ＆ インポート
"""

import os
import sys
import json
import datetime
import streamlit as st
import pandas as pd

from modules.workspace_manager import WorkspaceManager
from components.file_utils import count_lines

try:
    import duckdb
except ImportError:
    duckdb = None


def render_workspace_view(paths: dict, wm: WorkspaceManager):
    workspaces = wm.list_workspaces()
    current_ws_id = paths.get("WORKSPACE_ID")
    current_ws = wm.get_workspace(current_ws_id) if current_ws_id else None

    # =========================================================================
    # 初回起動・プロジェクト未作成時の専用ローンチ画面
    # =========================================================================
    if not workspaces:
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%); 
                    border: 1px solid #3b82f6; border-radius: 12px; padding: 28px; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 2.2rem;">📚</span>
                <div>
                    <h1 style="margin: 0; font-size: 1.8rem; color: #f8fafc;">JS-Refine Studio へようこそ</h1>
                    <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 1.05rem;">
                        人文学文化資源 メタデータ精緻化 ＆ 構造化システム
                    </p>
                </div>
            </div>
            <p style="margin-top: 16px; color: #cbd5e1; font-size: 0.95rem; line-height: 1.6;">
                本システムは、古典籍・古文書・美術工芸・近代文献・歴史資料など、<b>幅広い人文学・文化資源の研究対象</b>を持つ研究者のためのメタデータ精緻化プラットフォームです。<br>
                まずはあなたの研究対象に合わせた<b>新規研究プロジェクトを立ち上げる</b>ところから開始してください。
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("➕ 新規研究プロジェクトの立ち上げ")
        with st.form("init_create_workspace_form"):
            col_nw1, col_nw2 = st.columns(2)
            with col_nw1:
                new_name = st.text_input("プロジェクト表示名*", placeholder="例: 浮世絵・版画デジタルアーカイブ、近世文学史料")
                new_id = st.text_input("プロジェクトID（半角英数字・アンダースコア）*", placeholder="例: ukiyoe_prints, kinsei_literature")
                new_theme = st.text_input("研究対象・関心テーマ（Step 1の検索テーマに初期反映されます）", placeholder="例: 江戸時代中期・後期の浮世絵版画資料")
            with col_nw2:
                new_desc = st.text_area("プロジェクトの説明・研究目的", placeholder="例: 国立国会図書館および主要機関所蔵の浮世絵メタデータを網羅収集し、偽作・無関係資料を除外した確定データセットを構築する", height=125)

            submitted = st.form_submit_button("🚀 新規プロジェクトを作成して開始する", type="primary", use_container_width=True)
            if submitted:
                if not new_id or not new_name:
                    st.error("プロジェクトIDと表示名は必須です。")
                else:
                    try:
                        created = wm.create_workspace(new_id, new_name, description=new_desc, research_theme=new_theme)
                        st.session_state["active_workspace_id"] = created["id"]
                        st.session_state["main_menu_choice"] = "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得"
                        st.success(f"プロジェクト '{created['name']}' を立ち上げました！Step 1 へ進みます。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"作成エラー: {e}")

        st.markdown("---")
        with st.expander("📦 共同研究者から共有されたZIPパッケージから復元・インポート", expanded=False):
            st.caption("以前エクスポートした研究レシピや完全アーカイブ（ZIP）をお持ちの場合は、ここから復元して開始できます。")
            uploaded_file = st.file_uploader("ZIPパッケージを選択", type=["zip"], key="init_zip_upload")
            if uploaded_file is not None:
                custom_id = st.text_input("新規プロジェクトID（空欄で自動命名）", placeholder="例: imported_project", key="init_custom_id")
                custom_name = st.text_input("新規プロジェクト名（空欄で自動命名）", placeholder="例: 共有データセット", key="init_custom_name")
                if st.button("🚀 ワークスペースとして展開・インポート", type="primary", key="btn_init_import", use_container_width=True):
                    temp_dir = os.path.join(wm.data_root, "tmp_imports")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_zip = os.path.join(temp_dir, uploaded_file.name)
                    with open(temp_zip, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    try:
                        with st.spinner("パッケージを展開中..."):
                            imported_meta = wm.import_package(temp_zip, new_ws_id=custom_id or None, new_name=custom_name or None)
                            st.session_state["active_workspace_id"] = imported_meta["id"]
                            st.session_state["main_menu_choice"] = "Dashboard"
                            st.success(f"プロジェクト '{imported_meta['name']}' をインポートしました！")
                            st.rerun()
                    except Exception as e:
                        st.error(f"インポートエラー: {e}")
                    finally:
                        if os.path.exists(temp_zip):
                            os.remove(temp_zip)
        return

    # =========================================================================
    # 既存プロジェクトが存在する場合の通常画面
    # =========================================================================
    st.title("📁 プロジェクト ＆ 作業履歴マネージャー")
    st.caption("研究テーマの切り替え、フィルタリング経過の保存・ロールバック、共同研究者とのデータ引き継ぎを一括管理します。")

    if current_ws:
        # 現在のアクティブプロジェクト概要バナー
        col_info1, col_info2, col_info3 = st.columns([2, 1, 1])
        with col_info1:
            st.markdown(f"### 現在のプロジェクト: **{current_ws.get('name', current_ws_id)}** (`{current_ws_id}`)")
            if current_ws.get("research_theme"):
                st.caption(f"🎯 研究テーマ: **{current_ws.get('research_theme')}**")
            if current_ws.get("description"):
                st.info(current_ws.get("description"))
        with col_info2:
            disk_mb = current_ws.get("disk_size_bytes", 0) / (1024 * 1024)
            if disk_mb > 1024:
                st.metric("プロジェクト容量", f"{disk_mb / 1024:.2f} GB")
            else:
                st.metric("プロジェクト容量", f"{disk_mb:.1f} MB")
        with col_info3:
            raw_cnt = count_lines(paths.get("PATH_RAW_METADATA", ""))
            st.metric("初期メタデータ件数", f"{raw_cnt:,} 件")
    else:
        st.warning("⚠️ アクティブなプロジェクトが選択されていません。以下の一覧から切り替えるか、新規プロジェクトを作成してください。")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs([
        "📂 プロジェクト（ワークスペース）管理",
        "⏱️ フィルタリング作業履歴（スナップショット）",
        "📦 データ共有・他者引き継ぎ（エクスポート / インポート）"
    ])

    # =========================================================================
    # タブ 1: ワークスペース一覧・新規作成・切替・削除
    # =========================================================================
    with tab1:
        st.subheader("研究プロジェクト一覧")

        # テーブル/カード表示
        ws_cards_cols = st.columns(3)
        for idx, ws in enumerate(workspaces):
            with ws_cards_cols[idx % 3]:
                is_active = (ws["id"] == current_ws_id)
                border_color = "#3b82f6" if is_active else "#334155"
                bg_color = "rgba(59, 130, 246, 0.08)" if is_active else "rgba(30, 41, 59, 0.5)"
                active_badge = "<span style='background:#3b82f6;color:white;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;'>アクティブ</span>" if is_active else ""
                
                size_mb = ws.get("disk_size_bytes", 0) / (1024 * 1024)
                size_str = f"{size_mb / 1024:.2f} GB" if size_mb > 1024 else f"{size_mb:.1f} MB"
                theme_str = f"<div style='font-size:0.8rem; color:#60a5fa; margin-top:4px;'>🎯 {ws.get('research_theme')}</div>" if ws.get('research_theme') else ""

                st.markdown(f"""
                <div style="border: 2px solid {border_color}; background: {bg_color}; border-radius: 8px; padding: 14px; margin-bottom: 12px; min-height: 175px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; font-size:1.05rem;">{ws.get('name')}</h4>
                        {active_badge}
                    </div>
                    <div style="font-size:0.8rem; color:#94a3b8; margin-top:2px;">ID: <code>{ws.get('id')}</code></div>
                    {theme_str}
                    <p style="font-size:0.85rem; color:#cbd5e1; margin-top:6px; line-height:1.4; height:36px; overflow:hidden;">
                        {ws.get('description') or '（説明なし）'}
                    </p>
                    <div style="font-size:0.75rem; color:#64748b; margin-top:8px;">
                        💾 容量: {size_str} ｜ 作成日: {ws.get('created_at', '')[:10]}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                c1, c2 = st.columns([1, 1])
                with c1:
                    if not is_active:
                        if st.button(f"切り替え", key=f"btn_switch_{ws['id']}", use_container_width=True):
                            st.session_state["active_workspace_id"] = ws["id"]
                            st.rerun()
                    else:
                        st.button("選択中", key=f"btn_active_{ws['id']}", disabled=True, use_container_width=True)
                with c2:
                    if not is_active:
                        if st.button("削除", key=f"btn_del_{ws['id']}", type="secondary", use_container_width=True):
                            st.session_state[f"confirm_delete_{ws['id']}"] = True

                if st.session_state.get(f"confirm_delete_{ws['id']}", False):
                    st.warning(f"⚠️ 本当にプロジェクト '{ws['name']}' を削除しますか？データは完全に消去されます。")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("削除を確定", key=f"conf_y_{ws['id']}", type="primary", use_container_width=True):
                            wm.delete_workspace(ws["id"])
                            st.session_state[f"confirm_delete_{ws['id']}"] = False
                            st.success(f"プロジェクト '{ws['name']}' を削除しました。")
                            st.rerun()
                    with col_n:
                        if st.button("キャンセル", key=f"conf_n_{ws['id']}", use_container_width=True):
                            st.session_state[f"confirm_delete_{ws['id']}"] = False
                            st.rerun()

        st.markdown("---")
        st.subheader("➕ 新規プロジェクト（ワークスペース）作成")
        with st.form("create_workspace_form"):
            col_nw1, col_nw2 = st.columns(2)
            with col_nw1:
                new_id = st.text_input("プロジェクトID（半角英数字・アンダースコア）*", placeholder="例: ukiyoe_prints")
                new_name = st.text_input("プロジェクト表示名*", placeholder="例: 浮世絵・版画デジタルアーカイブ")
                new_theme = st.text_input("研究対象・関心テーマ", placeholder="例: 江戸時代の浮世絵版画資料")
            with col_nw2:
                new_desc = st.text_area("プロジェクトの説明・研究目的", placeholder="例: 国立国会図書館・東博所蔵の浮世絵メタデータ精緻化研究", height=105)

            clone_options = ["（初期ルールテンプレートを使用）"] + [f"{w['name']} ({w['id']})" for w in workspaces]
            selected_clone = st.selectbox("既存プロジェクトの判定ルール（About/Type/N-gram）を引き継ぐ", clone_options)

            submitted = st.form_submit_button("新規プロジェクトを作成して開始", type="primary", use_container_width=True)
            if submitted:
                if not new_id or not new_name:
                    st.error("プロジェクトIDと表示名は必須です。")
                else:
                    clone_id = None
                    if selected_clone != "（初期ルールテンプレートを使用）":
                        clone_id = selected_clone.split("(")[-1].rstrip(")")

                    try:
                        created = wm.create_workspace(new_id, new_name, description=new_desc, research_theme=new_theme, clone_from=clone_id)
                        st.session_state["active_workspace_id"] = created["id"]
                        st.session_state["main_menu_choice"] = "Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得"
                        st.success(f"プロジェクト '{created['name']}' を作成しました！自動的にアクティブに切り替えます。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"作成エラー: {e}")

    # =========================================================================
    # タブ 2: フィルタリング作業履歴（スナップショット保存・復元・タイムライン）
    # =========================================================================
    with tab2:
        st.subheader(f"⏱️ 作業履歴・スナップショット管理（対象: {current_ws.get('name')}）")
        st.caption("AboutルールやN-gramルールの試行錯誤の経過を保存・ロードできます。巨大な生データはそのまま、ルールと判定ステータスのみを超高速にロールバックします。")

        # 1. スナップショット保存フォーム
        with st.expander("📸 現在のフィルタリング判定・ルールをスナップショット保存", expanded=True):
            col_sn1, col_sn2 = st.columns([2, 1])
            with col_sn1:
                snap_name = st.text_input("スナップショット名*", placeholder="例: About第1弾判定完了（厳格フィルタ適用）")
                snap_desc = st.text_input("メモ・変更内容", placeholder="例: 768.1のみをOKにし、その他をGREYに設定した状態")
            with col_sn2:
                st.write("")
                st.write("")
                if st.button("💾 スナップショットを作成", type="primary", use_container_width=True):
                    if not snap_name:
                        st.error("スナップショット名を入力してください。")
                    else:
                        with st.spinner("スナップショットを生成中（Parquetダンプ・ルール退避）..."):
                            meta = wm.save_snapshot(current_ws_id, snap_name, snap_desc)
                            m = meta.get("metrics", {})
                            st.success(f"スナップショット '{meta['name']}' を保存しました！（採択: {m.get('adopted', 0):,} 件 / 除外: {m.get('discarded', 0):,} 件）")
                            st.rerun()

        # 2. スナップショット一覧タイムライン
        st.markdown("#### 📜 保存済みスナップショット一覧")
        snapshots = wm.list_snapshots(current_ws_id)

        if not snapshots:
            st.info("まだ保存されたスナップショットはありません。ルール調整の節目に上のフォームからスナップショットを作成してください。")
        else:
            for s in snapshots:
                s_id = s["id"]
                s_name = s.get("name", s_id)
                s_desc = s.get("description", "")
                s_date = s.get("created_at", "")[:19].replace("T", " ")
                m = s.get("metrics", {})

                with st.container():
                    st.markdown(f"""
                    <div style="border-left: 4px solid #3b82f6; background: rgba(30, 41, 59, 0.4); padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:600; font-size:1.05rem; color:#f8fafc;">🔖 {s_name}</span>
                            <span style="font-size:0.8rem; color:#94a3b8;">📅 {s_date}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#cbd5e1; margin-top:4px;">{s_desc or '（メモなし）'}</div>
                        <div style="margin-top:8px; display:flex; gap:16px; font-size:0.8rem;">
                            <span style="color:#22c55e;">✅ 採択: <b>{m.get('adopted', 0):,}</b> 件</span>
                            <span style="color:#ef4444;">🚫 除外: <b>{m.get('discarded', 0):,}</b> 件</span>
                            <span style="color:#eab308;">⚖️ 保留: <b>{m.get('grey', 0):,}</b> 件</span>
                            <span style="color:#94a3b8;">📊 母集団: <b>{m.get('total', 0):,}</b> 件</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    c_act1, c_act2, _ = st.columns([2, 1, 3])
                    with c_act1:
                        if st.button(f"⏪ この状態に復元（ロールバック）", key=f"restore_{s_id}", use_container_width=True):
                            st.session_state[f"confirm_restore_{s_id}"] = True

                    with c_act2:
                        if st.button("🗑️ 削除", key=f"del_snap_{s_id}", type="secondary", use_container_width=True):
                            wm.delete_snapshot(current_ws_id, s_id)
                            st.success(f"スナップショット '{s_name}' を削除しました。")
                            st.rerun()

                    if st.session_state.get(f"confirm_restore_{s_id}", False):
                        st.warning(f"⚠️ スナップショット '{s_name}' に復元しますか？ 現在のルールおよびDuckDBの判定ステータスがこの時点の状態に上書きされます。")
                        c_ry, c_rn = st.columns(2)
                        with c_ry:
                            if st.button("復元を実行", key=f"conf_ry_{s_id}", type="primary", use_container_width=True):
                                with st.spinner("スナップショットを復元中（ルール反映 ＆ DuckDB一括更新）..."):
                                    ok = wm.restore_snapshot(current_ws_id, s_id)
                                    st.session_state[f"confirm_restore_{s_id}"] = False
                                    if ok:
                                        st.success(f"スナップショット '{s_name}' の状態に正常復元しました！")
                                        st.rerun()
                                    else:
                                        st.error("復元処理中にエラーが発生しました。")
                        with c_rn:
                            if st.button("キャンセル", key=f"conf_rn_{s_id}", use_container_width=True):
                                st.session_state[f"confirm_restore_{s_id}"] = False
                                st.rerun()

    # =========================================================================
    # タブ 3: データ共有・他者引き継ぎ（エクスポート / インポート）
    # =========================================================================
    with tab3:
        st.subheader("📦 データ共有・他者引き継ぎパッケージ")
        st.caption("共同研究者への判定ルールの配布や、他環境への完全移行・アーカイブ用のZIPパッケージを生成・読み込みできます。")

        col_ex, col_im = st.columns(2)

        # エクスポート
        with col_ex:
            st.markdown("### 📤 プロジェクトのエクスポート")
            export_mode = st.radio(
                "パッケージ種別を選択:",
                [
                    "軽量レシピパッケージ (Recipe Bundle)",
                    "完全アーカイブパッケージ (Full Dataset Archive)"
                ],
                help="レシピは収集マニフェスト・ルール・査読ログのみ（数MB）。完全アーカイブは生データやDuckDBも含みます（数百MB〜GB）。"
            )

            exp_type = "recipe" if "軽量" in export_mode else "full"

            if st.button("📦 ZIPパッケージを生成して準備", type="primary", use_container_width=True):
                with st.spinner("パッケージを圧縮生成中..."):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_fname = f"{current_ws_id}_{exp_type}_{timestamp}.zip"
                    out_zip_path = os.path.join(paths["DIR_EXPORTS"], zip_fname)
                    wm.export_package(current_ws_id, out_zip_path, export_type=exp_type)
                    st.session_state["last_exported_zip"] = out_zip_path

            if "last_exported_zip" in st.session_state and os.path.exists(st.session_state["last_exported_zip"]):
                zip_p = st.session_state["last_exported_zip"]
                with open(zip_p, "rb") as fp:
                    st.download_button(
                        label=f"⬇️ {os.path.basename(zip_p)} をダウンロード ({os.path.getsize(zip_p) / (1024*1024):.2f} MB)",
                        data=fp,
                        file_name=os.path.basename(zip_p),
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )

        # インポート
        with col_im:
            st.markdown("### 📥 他者作成パッケージのインポート")
            uploaded_file = st.file_uploader("共有されたZIPパッケージを選択", type=["zip"])

            if uploaded_file is not None:
                st.info(f"アップロードされたファイル: **{uploaded_file.name}** ({uploaded_file.size / (1024*1024):.2f} MB)")
                
                custom_id = st.text_input("新規プロジェクトID（空欄の場合は自動命名）", placeholder="例: imported_colleague_study")
                custom_name = st.text_input("新規プロジェクト名（空欄の場合は自動命名）", placeholder="例: 〇〇先生提供データセット")

                if st.button("🚀 ワークスペースとして展開・インポート", type="primary", use_container_width=True):
                    # 一時保存
                    temp_dir = os.path.join(paths["DIR_DATA"], "tmp_imports")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_zip = os.path.join(temp_dir, uploaded_file.name)
                    with open(temp_zip, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    try:
                        with st.spinner("パッケージを展開・検証中..."):
                            imported_meta = wm.import_package(temp_zip, new_ws_id=custom_id or None, new_name=custom_name or None)
                            st.session_state["active_workspace_id"] = imported_meta["id"]
                            st.success(f"ワークスペース '{imported_meta['name']}' を正常に展開・インポートしました！")
                            st.rerun()
                    except Exception as e:
                        st.error(f"インポートエラー: {e}")
                    finally:
                        if os.path.exists(temp_zip):
                            os.remove(temp_zip)
