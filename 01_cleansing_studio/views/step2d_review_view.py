# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 2-D: 専門家最終査読ビュー
(DuckDB サーバーサイドページネーション ＆ 高速SQLフィルタリング対応版)
"""
import os
import streamlit as st

try:
    from modules.duckdb_manager import DuckDBManager
except (ImportError, ValueError):
    try:
        from duckdb_manager import DuckDBManager
    except ImportError:
        DuckDBManager = None

from modules.review_portal import load_merged_review_data, save_human_verified_data


def _calc_review_sources_signature(paths: dict) -> tuple:
    """査読に関わるソースファイルの更新日時シグネチャを計算"""
    files_to_check = [
        paths.get('PATH_RAW_METADATA'),
        paths.get('PATH_ABOUT_RULES', '01_cleansing_studio/rules/about_rules.json'),
        paths.get('PATH_NGRAM_RULES', '01_cleansing_studio/rules/ngram_rules.json'),
        paths.get('PATH_LLM_JUDGMENTS'),
        paths.get('PATH_VERIFIED_JSONL')
    ]
    sig = []
    for p in files_to_check:
        if p and os.path.exists(p):
            sig.append((p, os.path.getmtime(p), os.path.getsize(p)))
        else:
            sig.append((p, 0, 0))
    return tuple(sig)


def get_or_create_review_db(paths: dict, force_reload: bool = False):
    """
    査読ポータル用 DuckDBManager インスタンスの初期化・取得 (ファイルの変更検知付き自動再ロード)
    """
    current_sig = _calc_review_sources_signature(paths)
    cached_sig = st.session_state.get("duckdb_review_sig")
    cached_db = st.session_state.get("duckdb_review_manager")

    if not force_reload and cached_db is not None and cached_sig == current_sig:
        return cached_db

    if cached_db is not None:
        try:
            cached_db.close()
        except Exception:
            pass
        st.session_state["duckdb_review_manager"] = None

    if DuckDBManager is None:
        return None

    raw_metadata_path = paths['PATH_RAW_METADATA']
    if not os.path.exists(raw_metadata_path):
        return None

    # インメモリDBの生成とインポート
    db = DuckDBManager(":memory:")
    with st.spinner("DuckDBにメタデータおよび最新判定ログをロード中..."):
        db.import_jsonl(raw_metadata_path)

        # 既存のルール判定結果があれば反映
        about_rules_path = paths.get('PATH_ABOUT_RULES', '01_cleansing_studio/rules/about_rules.json')
        ngram_rules_path = paths.get('PATH_NGRAM_RULES', '01_cleansing_studio/rules/ngram_rules.json')
        import json
        about_rules = {}
        if os.path.exists(about_rules_path):
            try:
                with open(about_rules_path, 'r', encoding='utf-8') as f:
                    about_rules = json.load(f)
            except Exception:
                pass
        ngram_rules = {}
        if os.path.exists(ngram_rules_path):
            try:
                with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                    ngram_rules = json.load(f)
            except Exception:
                pass

        if about_rules or ngram_rules:
            db.apply_rules_fast(about_rules, ngram_rules)

        # LLM判定結果があればマージ
        llm_judgments_path = paths.get('PATH_LLM_JUDGMENTS')
        if llm_judgments_path and os.path.exists(llm_judgments_path):
            db.sync_llm_judgments(llm_judgments_path)

        # 過去の確定査読データ（手動オーバーライド）があれば自動復元
        verified_jsonl_path = paths.get('PATH_VERIFIED_JSONL')
        if verified_jsonl_path and os.path.exists(verified_jsonl_path):
            db.sync_human_decisions(verified_jsonl_path)

    st.session_state["duckdb_review_manager"] = db
    st.session_state["duckdb_review_sig"] = _calc_review_sources_signature(paths)
    return db


def render_step2d_view(paths: dict):
    """Step 4 画面の描画"""
    st.title("Step 4: 専門家による最終査読・手動オーバーライド")
    st.caption("自動ルールおよびLLMセマンティック判定結果、外部Web参照情報を総合検証し、専門家判断による最終判定（合格・除外）の確定と修正を行います。")

    raw_metadata_path = paths['PATH_RAW_METADATA']
    verified_jsonl_path = paths['PATH_VERIFIED_JSONL']

    if not os.path.exists(raw_metadata_path):
        st.warning("初期メタデータセットが存在しません。Step 1 を実行してください。")
        st.stop()

    # DuckDB 高速エンジンの初期化・ロード
    db = get_or_create_review_db(paths)

    # =========================================================================
    # 1. DuckDB 高速エンジン利用時（サーバーサイドページネーション）
    # =========================================================================
    if db is not None:
        metrics = db.get_review_metrics()
        total_records = metrics["total"]

        st.markdown("### 査読集約ステータスおよび判定修正状況 (⚡ DuckDB 高速集計)")
        c_m1, c_m2, c_m3, c_m4, c_m5 = st.columns([2.5, 2.5, 2.5, 2.5, 2])
        with c_m1:
            st.metric("総査読対象数", f"{total_records:,} 件")
        with c_m2:
            st.metric("LLM判定不能 (null)", f"{metrics['null_cnt']:,} 件")
        with c_m3:
            st.metric("現在の合格確定数", f"{metrics['pass_cnt']:,} 件")
        with c_m4:
            st.metric("判定修正 (オーバーライド) 数", f"{metrics['override_cnt']:,} 件", delta=f"{metrics['override_cnt']} 件を修正済み" if metrics['override_cnt'] > 0 else None)
        with c_m5:
            st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 データを再同期", help="Step 2のルールやStep 3のLLM判定結果をDuckDBへ強制再読み込みします", use_container_width=True):
                db = get_or_create_review_db(paths, force_reload=True)
                st.rerun()

        st.markdown("---")
        c_f1, c_f2, c_f3 = st.columns([2, 2, 2])
        with c_f1:
            filter_rev = st.selectbox(
                "絞り込みフィルタ:",
                [
                    "すべて",
                    "LLM判定不能 (null) データのみ",
                    "現在『合格』のデータのみ",
                    "現在『除外』のデータのみ",
                    "LLM判定経由データのみ",
                    "手動修正 (オーバーライド) データのみ"
                ]
            )
        with c_f2:
            search_rev = st.text_input("タイトル / ID / 理由検索:", placeholder="例: 殺生石 または 画譜", key="search_rev_portal")
        with c_f3:
            page_size_rev = st.selectbox("1ページの表示件数:", [10, 20, 50, 100], index=0, key="pg_size_rev")

        # ページネーション設定
        page_key = f"rev_page_num_{filter_rev}_{search_rev}_{page_size_rev}"
        if page_key not in st.session_state:
            st.session_state[page_key] = 1

        # サーバーサイド高速クエリ実行 (0.002秒)
        total_show, page_records = db.query_review_records(
            filter_type=filter_rev,
            search_query=search_rev,
            page=st.session_state[page_key],
            page_size=page_size_rev
        )

        total_pages = max(1, (total_show + page_size_rev - 1) // page_size_rev)
        if st.session_state[page_key] > total_pages:
            st.session_state[page_key] = total_pages

        c_p1, c_p2 = st.columns([3, 1])
        with c_p1:
            st.markdown(f"**該当件数: {total_show:,} 件** (全 {total_records:,} 件中)")
        with c_p2:
            rev_page_num = st.number_input(
                "ページ選択:",
                min_value=1,
                max_value=total_pages,
                value=st.session_state[page_key],
                step=1,
                key=f"num_input_{page_key}"
            )
            if rev_page_num != st.session_state[page_key]:
                st.session_state[page_key] = rev_page_num
                st.rerun()

        # 該当ページのみレンダリング (DOM負荷最小限)
        for r in page_records:
            rid = r["id"]
            auto_status = r["status"]
            cur_status = r["cur_status"]
            is_override = r["is_override"]

            with st.container(border=True):
                c_h1, c_h2 = st.columns([3, 1])
                with c_h1:
                    st.markdown(f"### {r['title']}")
                with c_h2:
                    badge_str = f"[合格]" if cur_status == "合格" else f"[除外]"
                    if is_override:
                        badge_str += " (手動修正済)"
                    st.markdown(f"### `{badge_str}`")

                st.info(f"自動判定判定理由: {r['reasons']}")

                ext_info = r.get("external_info", "")
                if ext_info and ext_info != "補足情報なし":
                    with st.expander("参照外部Web情報スニペット", expanded=False):
                        st.code(ext_info, language="text")

                c_r1, c_r2 = st.columns([3, 1])
                with c_r1:
                    with st.expander("資料メタデータ詳細 (ID / 原典)", expanded=False):
                        st.markdown(f"- **資料ID**: `{rid}`")
                        raw_item = r.get("raw_item", {})
                        if raw_item.get("schema:description"):
                            st.markdown(f"- **説明文**: {raw_item.get('schema:description')}")
                with c_r2:
                    new_status = st.radio(
                        "最終査読判定:",
                        ["合格", "除外"],
                        index=0 if cur_status == "合格" else 1,
                        key=f"rad_rev_{rid}",
                        horizontal=True
                    )
                    if new_status != cur_status:
                        db.set_human_decision(rid, new_status)
                        # 即時オートセーブによりリロードやクラッシュでも手動判定を安全保護
                        db.export_human_verified_data(verified_jsonl_path)
                        st.session_state["duckdb_review_sig"] = _calc_review_sources_signature(paths)
                        st.rerun()

        st.markdown("---")
        if st.button("最終査読確定データ (`human_verified_cleaned.jsonl`) の保存", type="primary", use_container_width=True):
            count = db.export_human_verified_data(verified_jsonl_path)
            st.session_state["duckdb_review_sig"] = _calc_review_sources_signature(paths)
            st.success(f"最終査読完了: 全 {count:,} 件の確定データを `{verified_jsonl_path}` に正常保存しました。")
        return

    # =========================================================================
    # 2. レガシーフォールバック (DuckDBが利用できない場合)
    # =========================================================================
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    llm_judgments_path = paths['PATH_LLM_JUDGMENTS']

    with st.spinner("全フェーズの判定結果および参照Web情報を集約中..."):
        review_records = load_merged_review_data(
            raw_jsonl_path=raw_metadata_path,
            about_filtered_path=about_filtered_path,
            type_filtered_path=type_filtered_path,
            ngram_filtered_path=ngram_filtered_path,
            llm_judgments_path=llm_judgments_path
        )

    if "human_decisions" not in st.session_state:
        st.session_state["human_decisions"] = {r["id"]: r["status"] for r in review_records}

    human_decisions = st.session_state["human_decisions"]
    override_cnt = sum(1 for r in review_records if human_decisions.get(r["id"]) != r["status"])

    st.markdown("### 査読集約ステータスおよび判定修正状況")
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    with c_m1:
        st.metric("総査読対象数", f"{len(review_records):,} 件")
    with c_m2:
        null_cnt = sum(1 for r in review_records if r.get("llm_target") is None and "LLM" in r.get("reasons", ""))
        st.metric("LLM判定不能 (null)", f"{null_cnt:,} 件")
    with c_m3:
        pass_cnt = sum(1 for r in review_records if human_decisions.get(r["id"]) == "合格")
        st.metric("現在の合格確定数", f"{pass_cnt:,} 件")
    with c_m4:
        st.metric("判定修正 (オーバーライド) 数", f"{override_cnt:,} 件", delta=f"{override_cnt} 件を人間が修正済み" if override_cnt > 0 else None)

    st.markdown("---")
    c_f1, c_f2, c_f3 = st.columns([2, 2, 2])
    with c_f1:
        filter_rev = st.selectbox(
            "絞り込みフィルタ:",
            [
                "すべて",
                "LLM判定不能 (null) データのみ",
                "現在『合格』のデータのみ",
                "現在『除外』のデータのみ",
                "LLM判定経由データのみ",
                "手動修正 (オーバーライド) データのみ"
            ]
        )
    with c_f2:
        search_rev = st.text_input("タイトル / ID / 理由検索:", placeholder="例: 殺生石 または 画譜", key="search_rev_portal")
    with c_f3:
        page_size_rev = st.selectbox("1ページの表示件数:", [10, 20, 50, 100], index=0, key="pg_size_rev")

    show_records = []
    for r in review_records:
        rid = r["id"]
        cur_status = human_decisions.get(rid, r["status"])
        is_override = (cur_status != r["status"])

        if filter_rev == "LLM判定不能 (null) データのみ":
            if not (r.get("llm_target") is None and "LLM" in r.get("reasons", "")):
                continue
        elif filter_rev == "現在『合格』のデータのみ" and cur_status != "合格":
            continue
        elif filter_rev == "現在『除外』のデータのみ" and cur_status != "除外":
            continue
        elif filter_rev == "LLM判定経由データのみ":
            if "LLM判定" not in r.get("reasons", "") or "LLMバイパス" in r.get("reasons", ""):
                continue
        elif filter_rev == "手動修正 (オーバーライド) データのみ" and not is_override:
            continue

        if search_rev.strip():
            sq = search_rev.strip().lower()
            if sq not in r["title"].lower() and sq not in rid.lower() and sq not in r["reasons"].lower() and sq not in str(r.get("llm_reason", "")).lower():
                continue

        show_records.append(r)

    total_show = len(show_records)
    total_pages = max(1, (total_show + page_size_rev - 1) // page_size_rev)

    c_p1, c_p2 = st.columns([3, 1])
    with c_p1:
        st.markdown(f"**該当件数: {total_show:,} 件** (全 {len(review_records):,} 件中)")
    with c_p2:
        rev_page_num = st.number_input("ページ選択:", min_value=1, max_value=total_pages, value=1, step=1, key="num_input_rev_page")

    start_idx = (rev_page_num - 1) * page_size_rev
    end_idx = min(start_idx + page_size_rev, total_show)
    page_records = show_records[start_idx:end_idx]

    for r in page_records:
        rid = r["id"]
        auto_status = r["status"]
        cur_status = human_decisions.get(rid, auto_status)
        is_override = (cur_status != auto_status)

        with st.container(border=True):
            c_h1, c_h2 = st.columns([3, 1])
            with c_h1:
                st.markdown(f"### {r['title']}")
            with c_h2:
                badge_str = f"[合格]" if cur_status == "合格" else f"[除外]"
                if is_override:
                    badge_str += " (手動修正済)"
                st.markdown(f"### `{badge_str}`")

            st.info(f"自動判定判定理由: {r['reasons']}")

            ext_info = r.get("external_info", "")
            if ext_info and ext_info != "補足情報なし":
                with st.expander("参照外部Web情報スニペット", expanded=False):
                    st.code(ext_info, language="text")

            c_r1, c_r2 = st.columns([3, 1])
            with c_r1:
                with st.expander("資料メタデータ詳細 (ID / 原典)", expanded=False):
                    st.markdown(f"- **資料ID**: `{rid}`")
                    raw_item = r.get("raw_item", {})
                    if raw_item.get("schema:description"):
                        st.markdown(f"- **説明文**: {raw_item.get('schema:description')}")
            with c_r2:
                new_status = st.radio(
                    "最終査読判定:",
                    ["合格", "除外"],
                    index=0 if cur_status == "合格" else 1,
                    key=f"rad_rev_{rid}",
                    horizontal=True
                )
                if new_status != cur_status:
                    human_decisions[rid] = new_status
                    st.rerun()

    st.markdown("---")
    if st.button("最終査読確定データ (`human_verified_cleaned.jsonl`) の保存", type="primary", use_container_width=True):
        count = save_human_verified_data(review_records, human_decisions, verified_jsonl_path)
        st.success(f"最終査読完了: 全 {count:,} 件の確定データを `{verified_jsonl_path}` に保存しました。")
