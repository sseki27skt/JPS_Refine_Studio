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
import streamlit as st

from components.file_utils import make_jps_item_url, safe_save_json
from modules.rule_filter import (
    extract_types_from_jsonl,
    load_type_rules,
    save_type_rules,
    apply_type_filter
)


def render_step2_type_view(paths: dict):
    raw_path = paths["PATH_RAW_METADATA"]
    type_rules_path = paths.get("PATH_TYPE_RULES", "01_cleansing_studio/rules/type_rules.json")
    type_filtered_path = paths.get("PATH_TYPE_FILTERED", "data/type_filtered.jsonl")

    st.title("Step 2-A: データ種別 (rdf:type) 分析・除外")
    st.caption("不要なリソース型（記事・論文、公演、絵画、木工、絵葉書など）をクリックして除外（🚫 NG）に設定します。誤合格防止のためTypeでは除外のみを適用します。")

    if not os.path.exists(raw_path) or os.path.getsize(raw_path) == 0:
        st.warning("⚠️ 初期メタデータセット (`data/raw_metadata.jsonl`) が見つかりません。先に Step 1 でデータを取得してください。")
        return

    # セッション状態の初期化
    if "draft_type_changes" not in st.session_state:
        st.session_state["draft_type_changes"] = {}

    draft_types = st.session_state["draft_type_changes"]

    # 1. データの抽出 ＆ 集計
    @st.cache_data(show_spinner="データ種別を分析中...")
    def get_cached_types(file_path, mtime, ver: int = 7):
        return extract_types_from_jsonl(file_path)

    raw_mtime = os.path.getmtime(raw_path)
    type_stats = get_cached_types(raw_path, raw_mtime, ver=7)

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
            st.markdown("#### 📊 絞り込み状況")
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
                if st.button(f"⚡ 仮設定 ({draft_cnt}件) を確定保存 ＆ フィルタ実行", type="primary", use_container_width=True, key="btn_apply_type_draft"):
                    for t_lbl, act in draft_types.items():
                        if act == "NG":
                            current_ng.add(t_lbl)
                        elif act == "RESET":
                            current_ng.discard(t_lbl)
                    draft_types.clear()

                    save_type_rules(type_rules_path, {"NG": current_ng, "OK": set()})
                    tot, pas, disc = apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                    st.success(f"保存完了（残存: {pas:,} 件 / 除外: {disc:,} 件）")
                    st.cache_data.clear()
                    st.rerun()
            else:
                if st.button("🔄 フィルタ再実行 (`type_filtered.jsonl` 更新)", use_container_width=True, key="btn_reapply_type_filter"):
                    tot, pas, disc = apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                    st.success(f"更新完了（残存: {pas:,} 件 / 除外: {disc:,} 件）")
                    st.rerun()

            st.write("---")
            st.markdown("##### 🚫 登録済除外種別")

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
                if st.button(f"⚡ 推奨ノイズ {len(avail_noise)} 種を一括除外", use_container_width=True, help=f"候補: {', '.join(avail_noise)}"):
                    for n in avail_noise:
                        draft_types[n] = "NG"
                    st.rerun()
            else:
                st.caption("推奨除外候補: 選択済")
        with c_bar3:
            if effective_ng or len(draft_types) > 0:
                if st.button("🔄 全除外を解除", key="btn_reset_all_types", use_container_width=True, help="すべてのデータ種別の除外設定を解除して初期状態（全保持）に戻します"):
                    for item in list(effective_ng) + list(draft_types.keys()):
                        draft_types[item] = "RESET"
                    current_ng.clear()
                    save_type_rules(type_rules_path, {"NG": set(), "OK": set()})
                    apply_type_filter(raw_path, type_filtered_path, type_rules_path)
                    draft_types.clear()
                    st.cache_data.clear()
                    st.success("すべての除外設定をクリアしました。")
                    st.rerun()

        # コンパクトな3列グリッド描画
        grid_cols = st.columns(3)
        for idx, t in enumerate(type_stats):
            col = grid_cols[idx % 3]
            t_lbl = t["short_label"]
            cnt = t["count"]
            full_uri = t["full_uri"]
            samples = t.get("samples", [])

            is_ng = (t_lbl in effective_ng)
            d_tag = " [仮除外]" if draft_types.get(t_lbl) == "NG" else (" [仮解除]" if draft_types.get(t_lbl) == "RESET" else "")

            btn_label = f"🚫 {t_lbl} ({cnt:,}件){d_tag}" if is_ng else f"📦 {t_lbl} ({cnt:,}件){d_tag}"
            btn_type = "primary" if is_ng else "secondary"

            c_btn, c_pop = col.columns([5, 1])
            with c_btn:
                if st.button(btn_label, key=f"btn_t_{idx}_{t_lbl}", type=btn_type, use_container_width=True, help=f"クリックして除外/解除を切替 (現在: {'除外' if is_ng else '保持'})"):
                    if is_ng:
                        draft_types[t_lbl] = "RESET"
                    else:
                        draft_types[t_lbl] = "NG"
                    st.rerun()

            with c_pop:
                with st.popover("🔍", help=f"『{t_lbl}』の資料例"):
                    st.markdown(f"#### 🔍 種別: {t_lbl}")
                    if full_uri:
                        st.caption(f"URI: `{full_uri}`")
                    st.markdown(f"- **件数**: **{cnt:,} 件** （{'🚫 除外対象' if is_ng else '✅ 保持'}）")
                    st.write("---")
                    st.caption(f"📄 サンプル資料 (全 {len(samples):,} 件):")
                    with st.container(height=320):
                        for s in samples:
                            s_title = s.get("title", "（無題）")
                            s_id = s.get("id", "")
                            s_creator = s.get("creator", "")
                            c_str = f" （著者: `{s_creator}`）" if s_creator else ""
                            item_link = make_jps_item_url(s_id, s_title)
                            st.markdown(f"• [📖 **{s_title}**]({item_link}){c_str}")
