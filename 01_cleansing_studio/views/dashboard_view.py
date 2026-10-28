# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Dashboard ビュー
"""
import streamlit as st
from components.file_utils import count_lines
from components.guide_card import navigate_to

def render_dashboard_view(paths: dict):
    """ダッシュボード画面を描画"""
    st.markdown("""
    <div class="cleanse-hero">
        <h1>JS-Refine Studio</h1>
        <p>人文学文化資源メタデータの網羅的抽出・多層ルールフィルタリング・LLMセマンティック適合判定・専門家査読を統合した精緻化システムです。</p>
    </div>
    """, unsafe_allow_html=True)

    # バックグラウンド実行中ステータスバナー
    from modules.sparql_collector import get_job_status
    status_file = paths.get("PATH_JOB_STATUS")
    st_data = get_job_status(status_file)
    if st_data.get("status") == "RUNNING":
        tot = st_data.get("total_target", 0)
        proc = st_data.get("processed_count", 0)
        stage_name = st_data.get("stage", "running")
        pct = (proc / max(1, tot)) * 100 if tot > 0 else 0.0
        eta = st_data.get("eta_seconds")
        eta_str = f"約 {eta // 60}分 {eta % 60}秒" if (eta is not None and eta > 0) else "計算中..."
        st.info(
            f"**バックグラウンドでメタデータ取得が進行中です**（ダッシュボード閲覧中も安全に継続されます）  \n"
            f"・ステージ: `{stage_name}` | 進捗: **{proc:,} / {tot:,} 件** ({pct:.1f}%) | 残り推定時間: **{eta_str}**"
        )
        if tot > 0:
            st.progress(min(1.0, proc / max(1, tot)))
        st.write("---")

    st.subheader("パイプライン全体進捗ダッシュボード")

    import os
    raw_metadata_path = paths.get('PATH_RAW_METADATA', '')
    duckdb_path = paths.get('PATH_DUCKDB', os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb") if raw_metadata_path else "")
    
    stats = None
    if duckdb_path and os.path.exists(duckdb_path):
        try:
            from modules.duckdb_manager import DuckDBManager
            db = DuckDBManager(duckdb_path)
            stats = db.get_prisma_flow_stats()
            db.close()
        except Exception:
            pass

    cols = st.columns(4)
    with cols[0]:
        val_step1 = stats["step1_raw"] if stats else count_lines(paths.get('PATH_RAW_METADATA'))
        st.metric("初期メタデータセット (Step 1)", f"{val_step1:,} 件")

    with cols[1]:
        val_2a = stats["step2a_type_survivors"] if stats else count_lines(paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl'))
        val_2b = stats["step2b_about_survivors"] if stats else count_lines(paths.get('PATH_ABOUT_FILTERED'))
        val_2c = stats["step2c_ngram_survivors"] if stats else count_lines(paths.get('PATH_NGRAM_FILTERED'))
        st.metric("2-A データ種別通過", f"{val_2a:,} 件")
        st.metric("2-B 主題キーワード通過", f"{val_2b:,} 件")
        st.metric("2-C タイトル文字列通過", f"{val_2c:,} 件")

    with cols[2]:
        val_s3 = stats["step3_llm_evaluated"] if stats else count_lines(paths.get('PATH_LLM_JUDGMENTS'))
        val_s4 = stats["step4_human_reviewed"] if stats else count_lines(paths.get('PATH_VERIFIED_JSONL'))
        st.metric("Step 3: LLM適合判定数", f"{val_s3:,} 件")
        st.metric("Step 4: 専門家確定数", f"{val_s4:,} 件")

    with cols[3]:
        val_s5 = stats["step5_export_ready"] if stats else count_lines(paths.get('PATH_EXPORT_JSON'))
        st.metric("統合検索用出力データ (Step 5)", f"{val_s5:,} 件")

    st.write("---")
    st.subheader("ワークフロー概要")
    st.markdown("""
    左側のサイドバーメニューより各工程を順次実行してください：
    1. **Step 1: クエリ拡張 ＆ Japan Searchメタデータ取得** （網羅的データ収集）
    2. **Step 2: 多層ルールベース・フィルタリング**
       - **Step 2-A: データ種別 (`rdf:type`) 分析・除外** （記事・絵画・公演・木工等の粗削り除外）
       - **Step 2-B: 主題 (`schema:about`) キーワード分析・判別** （NDC/NDLNA/件名による除外＆合格確定）
       - **Step 2-C: タイトル語彙・文字列パターン分析・除外** （頻出N-Gram/任意語彙による除外＆合格確定）
    3. **Step 3: LLMセマンティック適合判定** （ルールで確定しなかった保留群のみを文脈判定）
    4. **Step 4: 専門家による最終査読・手動オーバーライド** （全工程の統合検証・最終修正）
    5. **Step 5: 統合検索用データエクスポート** （ポータル用JSON/CSV出力）
    """)

    if st.button("データ収集を開始する (Step 1 へ進む) ->", type="primary"):
        navigate_to("Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得")

    st.write("---")
    # --- 全データリセットセクション ---
    st.subheader("システム初期化・全作業リセット")
    
    with st.container(border=True):
        st.markdown("""
        <div class="warning-banner">
            <h4>【警告】すべての作業データおよび設定ルールが完全に消去されます</h4>
            <p>
                この操作を実行すると、Japan Searchから収集した<b>初期メタデータセット（raw_metadata.jsonl）</b>、
                Step 2の<b>全フィルタリング結果（Type/About/N-Gram/LLM判定結果）</b>、
                構築された<b>除外・保持ルール設定（JSON）</b>、
                および<b>専門家査読データ</b>を含むすべてのファイルが<b>物理的に完全削除</b>されます。<br>
                この操作は取り消すことができません。
            </p>
        </div>
        """, unsafe_allow_html=True)

        confirm_reset = st.checkbox(
            "取得した初期メタデータセット、設定ルール、判定ログを含むすべてのデータを完全に削除し、ゼロからやり直すことを確認・同意しました",
            key="chk_confirm_full_reset"
        )

        c_rst1, c_rst2 = st.columns([1, 3])
        with c_rst1:
            if st.button("全データを初期化してリセット", type="primary", disabled=not confirm_reset, use_container_width=True):
                import os
                import time

                # 中間データ削除対象リスト（ルール定義ファイルは空JSONで安全初期化）
                data_dir = os.path.dirname(paths.get("PATH_RAW_METADATA", "data"))
                
                # ルール定義ファイル以外のデータ成果物を削除対象とする
                data_targets = [
                    paths.get("PATH_RAW_METADATA"),
                    paths.get("PATH_TARGET_URIS"),
                    paths.get("PATH_TYPE_FILTERED"),
                    paths.get("PATH_ABOUT_FILTERED"),
                    paths.get("PATH_NGRAM_FILTERED"),
                    paths.get("PATH_TARGET_FOR_LLM"),
                    paths.get("PATH_CONFIRMED_OK"),
                    paths.get("PATH_DISCARDED_RULES"),
                    paths.get("PATH_LLM_JUDGMENTS"),
                    paths.get("PATH_VERIFIED_JSONL"),
                    paths.get("PATH_EXPORT_JSON"),
                    paths.get("PATH_DUCKDB"),
                    paths.get("PATH_JOB_STATUS"),
                    os.path.join(data_dir, "fetch_job_status.json.tmp"),
                    os.path.join(data_dir, "metadata_store.duckdb.wal"),
                    os.path.join(data_dir, "current_fetch_params.json"),
                    os.path.join(data_dir, "cleaned_metadata.csv"),
                    os.path.join(data_dir, "discarded_about.csv"),
                    os.path.join(data_dir, "discarded_ngram.csv"),
                    os.path.join(data_dir, "discarded_suffix_filtered.csv"),
                    os.path.join(data_dir, "suffix_filtered.jsonl"),
                    os.path.join(data_dir, "tmp_llm_grey_judgments.jsonl"),
                    os.path.join(data_dir, "about_keywords_ranking.csv"),
                    os.path.join(data_dir, "vocab_ranking_scores.csv")
                ]

                deleted_count = 0
                for file_path in set(data_targets):
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception as e:
                            st.warning(f"削除スキップ: {file_path} ({e})")

                # ルール定義ファイルは物理削除せず空JSONで安全初期化
                import json
                type_r_path = paths.get("PATH_TYPE_RULES")
                if type_r_path:
                    os.makedirs(os.path.dirname(type_r_path), exist_ok=True)
                    with open(type_r_path, "w", encoding="utf-8") as f:
                        json.dump({"NG": [], "OK": []}, f, ensure_ascii=False, indent=2)

                for r_path in [paths.get("PATH_ABOUT_RULES"), paths.get("PATH_NGRAM_RULES")]:
                    if r_path:
                        os.makedirs(os.path.dirname(r_path), exist_ok=True)
                        with open(r_path, "w", encoding="utf-8") as f:
                            json.dump({}, f, ensure_ascii=False, indent=2)

                # キャッシュおよびセッション状態のクリア
                st.cache_data.clear()
                st.session_state.clear()

                st.success(f"初期化完了: 合計 {deleted_count} 個のデータファイルとキャッシュを完全消去しました。システムを初期状態へ再起動します...")
                time.sleep(1.2)
                st.rerun()

        with c_rst2:
            st.caption("※ チェックボックスにチェックを入れると初期化実行ボタンが有効化されます。")
