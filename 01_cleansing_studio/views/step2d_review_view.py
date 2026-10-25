# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 2-D: 専門家最終査読ビュー
"""
import os
import streamlit as st

from modules.review_portal import load_merged_review_data, save_human_verified_data

def render_step2d_view(paths: dict):
    """Step 4 画面の描画"""
    st.title("Step 4: 専門家による最終査読・手動オーバーライド")
    st.caption("自動ルールおよびLLMセマンティック判定結果、外部Web参照情報を総合検証し、専門家判断による最終判定（合格・除外）の確定と修正を行います。")

    raw_metadata_path = paths['PATH_RAW_METADATA']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    llm_judgments_path = paths['PATH_LLM_JUDGMENTS']
    verified_jsonl_path = paths['PATH_VERIFIED_JSONL']

    if not os.path.exists(raw_metadata_path):
        st.warning("初期メタデータセットが存在しません。Step 1 を実行してください。")
        st.stop()

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
