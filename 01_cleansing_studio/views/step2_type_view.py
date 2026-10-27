# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 2-A: データ種別 (rdf:type) 分析・除外ビュー
初期メタデータセットに含まれるリソース型（記事・論文、公演、絵画、図書、録音資料等）を分析し、
書誌作成において不要な種別を粗削り（大分類ノイズ除外）します。
※ データ種別ではOKルールを設けず、NG（確実な異物の除外）のみで安全に運用します。
"""

import os
import re
import json
import urllib.parse
import pandas as pd
import streamlit as st

from components.file_utils import make_jps_item_url, safe_save_json
from components.guide_card import render_guide_card, render_summary_banner, render_step_navigation
from modules.rule_filter import (
    extract_types_from_jsonl,
    load_type_rules,
    save_type_rules,
    apply_type_filter
)
from modules.duckdb_manager import DuckDBManager


def render_step2_type_view(paths: dict):
    raw_path = paths["PATH_RAW_METADATA"]
    type_rules_path = paths.get("PATH_TYPE_RULES", "01_cleansing_studio/rules/type_rules.json")
    type_filtered_path = paths.get("PATH_TYPE_FILTERED", "data/type_filtered.jsonl")
    duckdb_path = paths.get("PATH_DUCKDB", os.path.join(os.path.dirname(raw_path), "metadata_store.duckdb"))

    st.title("Step 2-A: データ種別 (rdf:type) 分析・除外")
    st.caption("不要なリソース型（記事・論文、公演、絵画、木工、絵葉書など）をクリックして除外（NG）に設定します。誤合格防止のためTypeでは除外のみを適用します。")

    render_guide_card(
        step_num="Step 2-A",
        step_title="データ種別 (rdf:type) 分析・除外",
        purpose="出版物・書籍以外の非該当データ種別（記事、公演、絵葉書など）を一括同定・除外します。",
        impact="除外対象のレコードに type_status = 'NG' がマークされ、後続ステップの評価母集団から除外されます（元データは保持）。",
        condition="対象外種別の除外ルールを保存・適用し、適切なデータ種別のみが残存すること。"
    )

    if not os.path.exists(raw_path) or os.path.getsize(raw_path) == 0:
        st.warning("初期メタデータセット (data/raw_metadata.jsonl) が見つかりません。先に Step 1 でデータを取得してください。")
        return

    # セッション状態の初期化
    if "draft_type_changes" not in st.session_state:
        st.session_state["draft_type_changes"] = {}

    draft_types = st.session_state["draft_type_changes"]

    # 1. DuckDB を用いた高速集計（DuckDB不在時のみ JSONL へフォールバック）
    has_duckdb = os.path.exists(duckdb_path) and os.path.getsize(duckdb_path) > 0

    @st.cache_data(show_spinner="データ種別を高速集計中 (DuckDB)...")
    def get_cached_types_duckdb(db_path: str, mtime: float):
        db = DuckDBManager(db_path=db_path)
        stats = db.get_type_stats()
        db.close()
        return stats

    @st.cache_data(show_spinner="データ種別を分析中 (JSONL)...")
    def get_cached_types_jsonl(file_path: str, mtime: float):
        return extract_types_from_jsonl(file_path)

    if has_duckdb:
        db_mtime = os.path.getmtime(duckdb_path)
        type_stats = get_cached_types_duckdb(duckdb_path, db_mtime)
    else:
        raw_mtime = os.path.getmtime(raw_path)
        type_stats = get_cached_types_jsonl(raw_path, raw_mtime)

    # 2. ルールの読み込み
    type_rules = load_type_rules(type_rules_path)
    current_ng = set(type_rules.get("NG", []))

    # 実効ルールの構築 (確定 + ドラフト)
    effective_ng = set(current_ng)
    for t_lbl, act in draft_types.items():
        if act == "NG":
            effective_ng.add(t_lbl)
        elif act == "RESET":
            effective_ng.discard(t_lbl)

    # 進捗メトリクスの計算
    total_raw_records = sum(t["count"] for t in type_stats)
    discarded_records = sum(t["count"] for t in type_stats if t["short_label"] in effective_ng)
    remaining_records = total_raw_records - discarded_records
    reduction_rate = (discarded_records / total_raw_records) if total_raw_records > 0 else 0.0

    # 2ペイン レイアウト（左: メイン操作領域 72% ｜ 右: 進捗＆確定パネル 28%）
    col_main, col_ctrl = st.columns([7.2, 2.8])

    # =========================================================================
    # 右側: 固定コントロール ＆ 進捗パネル
    # =========================================================================
    with col_ctrl:
        with st.container(border=True):
            st.markdown("#### 絞り込み状況")
            c_m1, c_m2 = st.columns(2)
            c_m1.metric("初期メタデータセット", f"{total_raw_records:,}")
            c_m2.metric("除外対象", f"{discarded_records:,}", delta=f"-{reduction_rate:.1%}", delta_color="inverse")
            
            c_m3, c_m4 = st.columns(2)
            c_m3.metric("残存見込", f"{remaining_records:,}")
            c_m4.metric("除外種別数", f"{len(effective_ng)} 件")

            st.write("---")

            # 確定 ＆ 保存ボタン
            draft_cnt = len(draft_types)
            if draft_cnt > 0:
                st.warning(f"現在 **{draft_cnt} 件** の仮設定があります。")
                if st.button(f"仮設定 ({draft_cnt}件) を確定保存 ＆ フィルタ実行", type="primary", use_container_width=True, key="btn_apply_type_draft"):
                    for t_lbl, act in draft_types.items():
                        if act == "NG":
                            current_ng.add(t_lbl)
                        elif act == "RESET":
                            current_ng.discard(t_lbl)
                    draft_types.clear()

                    def _execute_type_filter_with_provenance(target_ng):
                        save_type_rules(type_rules_path, {"NG": target_ng, "OK": set()})
                        tot, pas, disc = apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                        if os.path.exists(duckdb_path):
                            try:
                                db = DuckDBManager(db_path=duckdb_path)
                                db.apply_type_filter_fast(list(target_ng))
                                db.close()
                            except Exception:
                                pass
                        return tot, pas, disc

                    tot, pas, disc = _execute_type_filter_with_provenance(current_ng)
                    st.success(f"保存完了（残存: {pas:,} 件 / 除外: {disc:,} 件）")
                    st.cache_data.clear()
                    st.rerun()
            else:
                if st.button("フィルタ再実行 (type_filtered.jsonl 更新)", use_container_width=True, key="btn_reapply_type_filter"):
                    save_type_rules(type_rules_path, {"NG": current_ng, "OK": set()})
                    tot, pas, disc = apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                    if os.path.exists(duckdb_path):
                        try:
                            db = DuckDBManager(db_path=duckdb_path)
                            db.apply_type_filter_fast(list(current_ng))
                            db.close()
                        except Exception:
                            pass
                    st.success(f"更新完了（残存: {pas:,} 件 / 除外: {disc:,} 件）")
                    st.cache_data.clear()
                    st.rerun()

            st.write("---")
            st.markdown("##### 登録済除外種別")

            if effective_ng:
                for ng_item in sorted(list(effective_ng)):
                    c_n1, c_n2 = st.columns([4, 1])
                    c_n1.caption(f"• `{ng_item}`")
                    if c_n2.button("×", key=f"del_ng_type_{ng_item}", help="除外解除"):
                        draft_types[ng_item] = "RESET"
                        st.rerun()
            else:
                st.caption("除外 (NG) 種別はありません。")

    # =========================================================================
    # 左側: メイン分析・操作領域 (コンパクトな3列ピルボード形式)
    # =========================================================================
    with col_main:
        # クイック一括選択ツールバー
        c_bar1, c_bar2, c_bar3 = st.columns([4, 2.3, 1.7])
        with c_bar1:
            st.markdown(f"**データ種別一覧**（全 **{len(type_stats)}** 種別）: クリックで除外トグル")
        with c_bar2:
            typical_noise = ["記事・論文", "公演", "絵画", "絵葉書", "彫刻", "工芸品", "木工", "地図", "動画", "ウェブサイト"]
            avail_noise = [t["short_label"] for t in type_stats if any(n in t["short_label"] for n in typical_noise) and t["short_label"] not in effective_ng]
            if avail_noise:
                if st.button(f"推奨ノイズ {len(avail_noise)} 種を一括除外", use_container_width=True, help=f"候補: {', '.join(avail_noise)}"):
                    for n in avail_noise:
                        draft_types[n] = "NG"
                    st.rerun()
            else:
                st.caption("推奨除外候補: 選択済")
        with c_bar3:
            if effective_ng or len(draft_types) > 0:
                if st.button("全除外を解除", key="btn_reset_all_types", use_container_width=True, help="すべてのデータ種別の除外設定を解除して初期状態（全保持）に戻します"):
                    st.session_state["confirm_reset_all_types"] = True

        if st.session_state.get("confirm_reset_all_types", False):
            with st.container(border=True):
                st.warning("すべてのデータ種別の除外設定を解除し、初期状態（全保持）に戻しますか？")
                c_conf1, c_conf2 = st.columns([1, 1])
                with c_conf1:
                    if st.button("はい、全除外を解除します", type="primary", use_container_width=True, key="btn_confirm_reset_all_types"):
                        for item in list(effective_ng) + list(draft_types.keys()):
                            draft_types[item] = "RESET"
                        current_ng.clear()
                        save_type_rules(type_rules_path, {"NG": set(), "OK": set()})
                        apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                        draft_types.clear()
                        st.session_state["confirm_reset_all_types"] = False
                        st.cache_data.clear()
                        st.success("すべての除外設定をクリアしました。")
                        st.rerun()
                with c_conf2:
                    if st.button("キャンセル", use_container_width=True, key="btn_cancel_reset_all_types"):
                        st.session_state["confirm_reset_all_types"] = False
                        st.rerun()

        # コンパクトな3列グリッド描画
        grid_cols = st.columns(3)
        for idx, t in enumerate(type_stats):
            col = grid_cols[idx % 3]
            t_lbl = t["short_label"]
            cnt = t["count"]
            full_uri = t["full_uri"]

            is_ng = (t_lbl in effective_ng)
            d_tag = " [仮除外]" if draft_types.get(t_lbl) == "NG" else (" [仮解除]" if draft_types.get(t_lbl) == "RESET" else "")

            btn_label = f"[除外] {t_lbl} ({cnt:,}件){d_tag}" if is_ng else f"{t_lbl} ({cnt:,}件){d_tag}"
            btn_type = "primary" if is_ng else "secondary"

            c_btn, c_pop = col.columns([4.8, 1.2])
            with c_btn:
                if st.button(btn_label, key=f"btn_t_{idx}_{t_lbl}", type=btn_type, use_container_width=True, help=f"クリックして除外/解除を切替 (現在: {'除外' if is_ng else '保持'})"):
                    if is_ng:
                        draft_types[t_lbl] = "RESET"
                    else:
                        draft_types[t_lbl] = "NG"
                    st.rerun()

            with c_pop:
                with st.popover("詳細", help=f"『{t_lbl}』の資料一覧"):
                    st.markdown(f"#### 種別: {t_lbl}")
                    if full_uri:
                        st.caption(f"URI: `{full_uri}`")
                    st.markdown(f"- **総件数**: **{cnt:,} 件** （{'除外対象' if is_ng else '保持'}）")
                    st.write("---")

                    # DuckDB からオンデマンドで代表資料を取得（最大100件）
                    if has_duckdb:
                        @st.cache_data(show_spinner=False)
                        def _get_samples_for_popover(db_path: str, target_label: str, limit: int = 100):
                            db = DuckDBManager(db_path=db_path)
                            recs = db.get_records_by_type(target_label, limit=limit)
                            db.close()
                            return recs

                        sample_docs = _get_samples_for_popover(duckdb_path, t_lbl, limit=100)
                    else:
                        sample_docs = t.get("samples", [])[:100]

                    st.caption(f"資料一覧 (上位 {len(sample_docs):,} 件 / 全 {cnt:,} 件):")
                    if sample_docs:
                        df_samples = pd.DataFrame([{
                            "タイトル": s.get("title", "（無題）"),
                            "Japan Search": make_jps_item_url(s.get("id", ""), s.get("title", "")),
                            "概要": (s.get("description", "") or "")[:120]
                        } for s in sample_docs])

                        st.dataframe(
                            df_samples,
                            column_config={
                                "Japan Search": st.column_config.LinkColumn("JPSリンク", display_text="開く"),
                                "タイトル": st.column_config.TextColumn("タイトル", width="medium"),
                                "概要": st.column_config.TextColumn("概要", width="large")
                            },
                            width="stretch",
                            height=280,
                            hide_index=True
                        )
                    else:
                        st.info("該当する資料が見つかりませんでした。")

        # =====================================================================
        # フィルタリングによって影響を受ける全てのファイル（除外対象一覧）
        # =====================================================================
        st.write("---")
        st.markdown("### フィルタリング影響を受ける除外対象一覧")

        if discarded_records > 0:
            st.info(
                f"現在、**{len(effective_ng)} 種別**（`{', '.join(sorted(list(effective_ng)))}`）が除外対象として選択されています。"
                f"合計 **{discarded_records:,} 件** のファイルが除外（フィルタリング影響）を受けます。"
            )

            # サーバーサイド・ページネーション設定 (50件単位)
            page_key = "step2_type_disc_page"
            if page_key not in st.session_state:
                st.session_state[page_key] = 1

            search_key = "step2_type_disc_search"
            c_d_search, c_d_meta = st.columns([7, 3])
            with c_d_search:
                disc_search_query = st.text_input(
                    "除外資料内を検索 (タイトル / ID / 説明):",
                    key=search_key,
                    placeholder="例: 論文、浮世絵、あるいはIDを入力..."
                )
            with c_d_meta:
                page_size = 50
                st.caption(f"表示単位: **{page_size} 件 / ページ** (サーバーサイド取得)")

            cur_page = st.session_state.get(page_key, 1)

            if has_duckdb:
                db = DuckDBManager(db_path=duckdb_path)
                total_disc_count, page_records = db.query_records_discarded_by_types(
                    ng_types=list(effective_ng),
                    search_query=disc_search_query,
                    page=cur_page,
                    page_size=page_size
                )
                db.close()
            else:
                total_disc_count, page_records = 0, []

            total_pages = max(1, (total_disc_count + page_size - 1) // page_size)
            if cur_page > total_pages:
                cur_page = total_pages
                st.session_state[page_key] = cur_page

            if total_disc_count > 0:
                df_disc = pd.DataFrame([{
                    "タイトル": r.get("title", "（無題）"),
                    "除外理由 (該当種別)": r.get("matched_type", ""),
                    "Japan Search": make_jps_item_url(r.get("id", ""), r.get("title", "")),
                    "概要": (r.get("description", "") or "")[:150],
                    "ID": r.get("id", "")
                } for r in page_records])

                col_d_hdr, col_d_btn = st.columns([7.5, 2.5])
                with col_d_hdr:
                    st.caption(
                        f"除外対象: 全 **{total_disc_count:,} 件** 中 "
                        f"**{(cur_page - 1) * page_size + 1:,} 〜 {min(cur_page * page_size, total_disc_count):,} 件目** を表示 "
                        f"(ページ **{cur_page} / {total_pages}**):"
                    )
                with col_d_btn:
                    if has_duckdb:
                        # オンデマンドでエクスポート用のCSVを生成（メモリ浪費なし）
                        @st.cache_data(show_spinner="除外全件CSVを生成中...")
                        def _get_discarded_csv_data(db_path: str, ng_tuple: tuple, mtime: float):
                            d_db = DuckDBManager(db_path=db_path)
                            _, all_disc = d_db.query_records_discarded_by_types(list(ng_tuple), page=1, page_size=1000000)
                            d_db.close()
                            df_all = pd.DataFrame([{
                                "タイトル": r.get("title", "（無題）"),
                                "除外理由 (該当種別)": r.get("matched_type", ""),
                                "Japan Search": make_jps_item_url(r.get("id", ""), r.get("title", "")),
                                "概要": r.get("description", "") or "",
                                "ID": r.get("id", "")
                            } for r in all_disc])
                            return df_all.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')

                        csv_bytes = _get_discarded_csv_data(
                            duckdb_path,
                            tuple(sorted(list(effective_ng))),
                            db_mtime
                        )
                    else:
                        csv_bytes = df_disc.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')

                    st.download_button(
                        label="除外全件をCSVダウンロード",
                        data=csv_bytes,
                        file_name="discarded_type_records.csv",
                        mime="text/csv",
                        use_container_width=True,
                        help="フィルタリングによって除外されるすべての資料のリストをCSVで保存します"
                    )

                st.dataframe(
                    df_disc,
                    column_config={
                        "Japan Search": st.column_config.LinkColumn("JPSリンク", display_text="開く"),
                        "タイトル": st.column_config.TextColumn("タイトル", width="medium"),
                        "除外理由 (該当種別)": st.column_config.TextColumn("除外種別", width="small"),
                        "概要": st.column_config.TextColumn("概要", width="large"),
                        "ID": st.column_config.TextColumn("ID", width="medium")
                    },
                    width="stretch",
                    height=380,
                    hide_index=True
                )

                # サーバーサイド・ページネーション コントロール
                c_prev, c_page_info, c_next = st.columns([1.5, 3, 1.5])
                with c_prev:
                    if st.button("前へ", disabled=(cur_page <= 1), key="btn_prev_type_disc", use_container_width=True):
                        st.session_state[page_key] = max(1, cur_page - 1)
                        st.rerun()
                with c_page_info:
                    new_page = st.number_input(
                        "ページ選択:",
                        min_value=1,
                        max_value=total_pages,
                        value=cur_page,
                        step=1,
                        key="num_input_type_disc_page"
                    )
                    if new_page != cur_page:
                        st.session_state[page_key] = new_page
                        st.rerun()
                with c_next:
                    if st.button("次へ", disabled=(cur_page >= total_pages), key="btn_next_type_disc", use_container_width=True):
                        st.session_state[page_key] = min(total_pages, cur_page + 1)
                        st.rerun()
            else:
                st.info("該当する除外データは見つかりませんでした。")
        else:
            st.success("現在、除外 (NG) に設定されたデータ種別はありません。初期母集団のすべての資料が保持対象となります。")

    # 最下部ナビゲーション
    render_step_navigation(
        prev_choice="Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得",
        next_choice="Step 2-B: 主題 (schema:about) キーワード分析・判別"
    )
