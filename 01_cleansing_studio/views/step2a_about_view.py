# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 2-A: 主題 (schema:about) キーワード分析・判別ビュー
"""
import json
import math
import os
import re
import urllib.parse
from collections import defaultdict
import streamlit as st
import streamlit.components.v1 as components

from components.file_utils import safe_save_json, make_rich_search_links_md, make_rich_search_links
from components.pill_board import render_pill_board
from modules.rule_filter import (
    run_about_filter,
    suggest_ng_keywords_with_llm,
    extract_about_keywords_from_jsonl,
    extract_about_values
)

try:
    import streamlit_hotkeys as hotkeys
except Exception:
    hotkeys = None

@st.cache_data(show_spinner=False)
def cluster_about_keywords(about_ranking_tuples: list):
    """AboutキーワードをNDC分類（公式API）・階層構造および共通プレフィックス・バケットで超高速クラスタリング（キャッシュ済）"""
    if not about_ranking_tuples:
        return []
    
    from components.ndc_utils import (
        extract_ndc_number, 
        resolve_ndc_label, 
        format_about_keyword_display
    )

    ndc_groups = defaultdict(list)
    ndlna_items = []
    prefix_groups = defaultdict(list)
    unassigned = []
    
    from components.ndc_utils import extract_ndlna_id, resolve_ndlna_label

    # 1. NDCコード / NDLNA典拠 / 階層区切り文字による分類
    for kw, count in about_ranking_tuples:
        # A. NDCコードの判定
        ndc_num = extract_ndc_number(kw)
        if ndc_num:
            base_ndc = ndc_num.split('.')[0] if '.' in ndc_num else ndc_num
            ndc_groups[base_ndc].append((kw, count))
            continue

        # B. NDLNA / NDLSH 典拠の判定
        auth_id = extract_ndlna_id(kw)
        if auth_id:
            ndlna_items.append((kw, count))
            continue

        # C. 階層区切り文字（--, /, :, _, ･, 空白）
        if "--" in kw:
            parts = kw.split("--")
            parent = "--".join(parts[:-1]) if len(parts) > 1 else parts[0]
            prefix_groups[parent].append((kw, count))
        else:
            m = re.match(r'^(.*?)(?:[/:\s_･]+)(.+)$', kw)
            if m and len(m.group(1).strip()) >= 2:
                parent = m.group(1).strip()
                prefix_groups[parent].append((kw, count))
            else:
                unassigned.append((kw, count))
            
    clusters = []
    cluster_idx = 0
    
    # 2. NDC分類クラスタの生成 (公式APIに基づくラベル付与)
    for base_ndc, items in ndc_groups.items():
        items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
        total_cnt = sum(c for k, c in items_sorted)
        lbl_str, is_exact, parent_c = resolve_ndc_label(base_ndc)
        tag_lbl = f" [{lbl_str}]" if lbl_str else ""
        clusters.append({
            "cluster_id": f"cl_ndc_{cluster_idx}",
            "name": f"🏷️ NDC分類: {base_ndc}{tag_lbl}",
            "keywords": [k for k, c in items_sorted],
            "total_count": total_cnt
        })
        cluster_idx += 1

    # 3. NDLNA 典拠クラスタの生成
    if ndlna_items:
        items_sorted = sorted(ndlna_items, key=lambda x: x[1], reverse=True)
        total_cnt = sum(c for k, c in items_sorted)
        clusters.append({
            "cluster_id": f"cl_ndlna_{cluster_idx}",
            "name": f"👥 NDLNA 典拠（人名・件名・団体名）",
            "keywords": [k for k, c in items_sorted],
            "total_count": total_cnt
        })
        cluster_idx += 1

    # 4. 階層プレフィックスクラスタの生成
    for pkey, items in prefix_groups.items():
        if len(items) >= 2:
            items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
            total_cnt = sum(c for k, c in items_sorted)
            disp_pkey = format_about_keyword_display(pkey, max_label_len=28)
            clusters.append({
                "cluster_id": f"cl_p_{cluster_idx}",
                "name": f"階層: {disp_pkey}",
                "keywords": [k for k, c in items_sorted],
                "total_count": total_cnt
            })
            cluster_idx += 1
        else:
            unassigned.extend(items)
            
    # 5. 残りの未分類キーワードを先頭2文字の共通プレフィックスでバケット分類
    bucket_groups = defaultdict(list)
    for kw, cnt in unassigned:
        prefix_key = kw[:2] if len(kw) >= 2 else kw
        bucket_groups[prefix_key].append((kw, cnt))
        
    for bkey, bitems in bucket_groups.items():
        if len(bitems) >= 2:
            bitems_sorted = sorted(bitems, key=lambda x: x[1], reverse=True)
            rep_name = bitems_sorted[0][0]
            disp_rep = format_about_keyword_display(rep_name, max_label_len=25)
            total_cnt = sum(c for k, c in bitems_sorted)
            clusters.append({
                "cluster_id": f"cl_b_{cluster_idx}",
                "name": f"関連: {disp_rep} グループ",
                "keywords": [k for k, c in bitems_sorted],
                "total_count": total_cnt
            })
            cluster_idx += 1
        else:
            kw1, cnt1 = bitems[0]
            disp_kw1 = format_about_keyword_display(kw1, max_label_len=30)
            clusters.append({
                "cluster_id": f"cl_s_{cluster_idx}",
                "name": f"単一: {disp_kw1}",
                "keywords": [kw1],
                "total_count": cnt1
            })
            cluster_idx += 1
            
    clusters.sort(key=lambda x: x["total_count"], reverse=True)
    return clusters


def render_step2a_view(paths: dict):
    """Step 2-B 画面の描画"""
    st.title("Step 2-B: 主題 (schema:about) キーワード分析・判別")
    st.markdown("取得データに含まれる `schema:about` キーワード（NDC分類、NDLNA典拠、件名）を解析し、除外対象（🚫 NG）および合格確定（✅ OK: LLMスキップ）の判定を行います。")

    raw_metadata_path = paths['PATH_RAW_METADATA']
    about_rules_path = paths['PATH_ABOUT_RULES']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    ngram_rules_path = paths.get('PATH_NGRAM_RULES', '01_cleansing_studio/rules/ngram_rules.json')
    ngram_filtered_path = paths.get('PATH_NGRAM_FILTERED', 'data/ngram_filtered.jsonl')

    if not os.path.exists(raw_metadata_path):
        st.warning("先に Step 1 で初期メタデータセット (raw_metadata.jsonl) を取得してください。")
        st.stop()

    os.makedirs(os.path.dirname(about_rules_path), exist_ok=True)

    # --- 📁 入力データソースの選択 ＆ 前段/後段 相互連携コントロール ---
    data_source_options = []
    if os.path.exists(type_filtered_path):
        data_source_options.append("Step 2-A (データ種別) 適用後データ (type_filtered.jsonl)")
    if os.path.exists(ngram_filtered_path):
        data_source_options.append("Step 2-C (タイトル文字列) 適用後データ (ngram_filtered.jsonl)")
    data_source_options.append("初期メタデータセット全件 (raw_metadata.jsonl)")

    c_src1, c_src2 = st.columns([3, 2])
    with c_src1:
        chosen_source = st.selectbox(
            "📁 分析対象データソース:",
            options=data_source_options,
            index=0,
            help="前段で除外されたデータ種別やタイトルノイズをあらかじめ省いた状態で Step 2-B の分析を行うことができます。",
            key="sb_step2a_data_source"
        )
    
    if "type_filtered" in chosen_source:
        input_path = type_filtered_path
    elif "ngram_filtered" in chosen_source:
        input_path = ngram_filtered_path
    else:
        input_path = raw_metadata_path

    input_mtime = os.path.getmtime(input_path) if os.path.exists(input_path) else 0

    with c_src2:
        has_ngram_rules = os.path.exists(ngram_rules_path)
        link_ngram_rules = False
        if has_ngram_rules and "ngram_filtered" not in chosen_source:
            link_ngram_rules = st.toggle(
                "⚡ Step 2-C (タイトルNGルール) をリアルタイム連動",
                value=False,
                help="Step 2-C で登録済みのタイトル除外ルールに一致するレコードを、Step 2-B のシミュレーション上でも除外扱いにして分析します。",
                key="tgl_step2a_link_ngram"
            )
        elif "ngram_filtered" in chosen_source:
            st.success("✅ Step 2-C の除外結果を反映したデータセットで分析中")

    # Step 2-C タイトル NG ルールのロード (リアルタイム連動用)
    ngram_ng_set = set()
    if link_ngram_rules and os.path.exists(ngram_rules_path):
        try:
            with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                ng_r = json.load(f)
                ngram_ng_set = set([k for k, v in ng_r.items() if v == "NG"])
        except Exception:
            ngram_ng_set = set()

    @st.cache_data(show_spinner=False)
    def load_raw_item_features(path, mtime):
        about_ranking = extract_about_keywords_from_jsonl(path)
        records_data = []
        kw_to_doc_indices = defaultdict(list)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                idx = 0
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        about_list = item.get("schema:about", [])
                        kw_set = set(extract_about_values(about_list))

                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)

                        desc_val = item.get("schema:description", "")
                        desc_str = str(desc_val[0]) if isinstance(desc_val, list) and desc_val else str(desc_val)

                        creator_val = item.get("schema:creator", "")
                        creator_str = str(creator_val[0]) if isinstance(creator_val, list) and creator_val else str(creator_val)

                        records_data.append({
                            "id": item.get("@id", item.get("id", "")),
                            "title": title_str,
                            "desc": desc_str,
                            "creator": creator_str,
                            "about_set": list(kw_set)
                        })
                        for kw in kw_set:
                            kw_to_doc_indices[kw].append(idx)
                        idx += 1
                    except Exception:
                        continue
        return about_ranking, records_data, dict(kw_to_doc_indices)

    about_ranking, raw_records, kw_to_doc_indices = load_raw_item_features(input_path, input_mtime)

    if not about_ranking:
        st.info("データ内に schema:about キーワードが見つかりませんでした。")
        st.stop()
    
    # 常に about_rules.json とセッションステートを同期ロード
    rules = {}
    if os.path.exists(about_rules_path):
        try:
            with open(about_rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
        except Exception:
            pass

    if "edited_noise" not in st.session_state:
        st.session_state["edited_noise"] = set([k for k, v in rules.items() if v == "NG"])
    else:
        st.session_state["edited_noise"].update([k for k, v in rules.items() if v == "NG"])

    if "edited_strong" not in st.session_state:
        st.session_state["edited_strong"] = set([k for k, v in rules.items() if v == "OK"])
    else:
        st.session_state["edited_strong"].update([k for k, v in rules.items() if v == "OK"])

    current_ng = st.session_state["edited_noise"]
    current_ok = st.session_state["edited_strong"]

    if "checked_words" not in st.session_state:
        st.session_state["checked_words"] = set()
    if "chk_view_ver" not in st.session_state:
        st.session_state["chk_view_ver"] = 0
    if "draft_about_changes" not in st.session_state:
        st.session_state["draft_about_changes"] = {}
    draft_ab = st.session_state["draft_about_changes"]

    # フィルタフラグの永続セッション保持
    if "persistent_hide_classified" not in st.session_state:
        st.session_state["persistent_hide_classified"] = False
    if "persistent_hide_zero_pills" not in st.session_state:
        st.session_state["persistent_hide_zero_pills"] = False

    checked_words = st.session_state["checked_words"]

    # レコード（メタデータ件数）ベースの超高速シミュレーション
    total_records_cnt = len(raw_records)
    total_about_types = len(about_ranking)
    
    # 確定済みルール + 現在の仮設定ルールを統合してリアルタイム計算
    draft_ng = set(k for k, v in draft_ab.items() if v == "NG")
    draft_ok = set(k for k, v in draft_ab.items() if v == "OK")
    draft_reset = set(k for k, v in draft_ab.items() if v == "RESET")

    live_ng = (set(current_ng) | draft_ng) - draft_reset
    live_ok = (set(current_ok) | draft_ok) - draft_reset
    
    all_about_kws = list(kw_to_doc_indices.keys())
    exact_ng = set(live_ng)
    exact_ok = set(live_ok)
    ng_partial = [w for w in live_ng if len(w) >= 2]
    ok_partial = [w for w in live_ok if len(w) >= 2]
    
    matched_ng_kws = set()
    for kw in all_about_kws:
        if kw in exact_ng:
            matched_ng_kws.add(kw)
        else:
            for ng_w in ng_partial:
                if ng_w in kw:
                    matched_ng_kws.add(kw)
                    break
                    
    matched_ok_kws = set()
    for kw in all_about_kws:
        if kw in matched_ng_kws:
            continue
        if kw in exact_ok:
            matched_ok_kws.add(kw)
        else:
            for ok_w in ok_partial:
                if ok_w in kw:
                    matched_ok_kws.add(kw)
                    break

    ng_doc_indices = set()
    for kw in matched_ng_kws:
        ng_doc_indices.update(kw_to_doc_indices[kw])

    # Step 2-B N-Gram ルールによる事前除外の加算 (連動時)
    if ngram_ng_set:
        ngram_pat = re.compile("|".join(re.escape(k) for k in sorted(ngram_ng_set, key=len, reverse=True)))
        for idx, rec in enumerate(raw_records):
            t_str = rec.get("title", "")
            if ngram_pat.search(t_str):
                ng_doc_indices.add(idx)

    active_doc_indices = set(range(total_records_cnt)) - ng_doc_indices
    discarded_records_cnt = len(ng_doc_indices)
    remaining_records_cnt = len(active_doc_indices)
    reduction_rate = discarded_records_cnt / max(1, total_records_cnt)

    all_kw_set = set([k for k, c in about_ranking])
    ng_classified_count = len(all_kw_set & live_ng)
    ok_classified_count = len(all_kw_set & live_ok)
    unclassified_count = total_about_types - ng_classified_count - ok_classified_count

    # クラスタリングの実行 (O(N) 高速計算)
    about_clusters = cluster_about_keywords(about_ranking)

    # 3カラム / 2ペイン レイアウト（左: メイン作業領域 70% ｜ 右: 固定コントロール＆進捗パネル 30%）
    col_main, col_ctrl = st.columns([7, 3])

    # =========================================================================
    # 右側: 固定コントロール ＆ アクションパネル
    # =========================================================================
    with col_ctrl:
        st.markdown("### 🎛️ コントロール ＆ 進捗")
        
        # 0. 個別ピルのクリック判定モード
        st.markdown("##### 🎯 個別ピルのクリック判定モード")
        if "click_action_about_mode" not in st.session_state:
            st.session_state["click_action_about_mode"] = "NGに設定"

        click_mode_options = [
            "🚫 NG (除外) に設定",
            "✅ OK (保持) に設定",
            "❓ 未判定に戻す",
            "🔄 3段階トグル切替"
        ]
        mode_map = {
            "🚫 NG (除外) に設定": "NGに設定",
            "✅ OK (保持) に設定": "OKに設定",
            "❓ 未判定に戻す": "未判定に戻す",
            "🔄 3段階トグル切替": "トグル切替"
        }
        rev_mode_map = {v: k for k, v in mode_map.items()}

        cur_mode_val = st.session_state.get("click_action_about_mode", "NGに設定")
        cur_mode_disp = rev_mode_map.get(cur_mode_val, "🚫 NG (除外) に設定")

        chosen_disp = st.radio(
            "ピルクリック時の動作:",
            options=click_mode_options,
            index=click_mode_options.index(cur_mode_disp) if cur_mode_disp in click_mode_options else 0,
            key="rb_global_click_mode",
            help="クラスタ内および単体ボードの各ピルをクリックした際の判定動作を設定します。"
        )
        st.session_state["click_action_about_mode"] = mode_map[chosen_disp]
        st.caption("⌨️ キーボード: **Q** = NGモード ｜ **W** = OKモード ｜ **E** = リセット")

        st.write("---")

        # 1. 絞り込み進捗メトリクス
        st.markdown("##### 📊 絞り込み進捗 (レコード件数)")
        st.metric("初期メタデータセット", f"{total_records_cnt:,} 件")
        st.metric(
            "About 除外 (削ぎ落とし)", 
            f"{discarded_records_cnt:,} 件", 
            delta=f"-{reduction_rate:.1%}", 
            delta_color="inverse",
            help="schema:aboutにNGキーワードが含まれるため本工程で除外されるメタデータ件数"
        )
        st.metric(
            "本工程通過残存レコード", 
            f"{remaining_records_cnt:,} 件", 
            delta=f"{remaining_records_cnt/max(1, total_records_cnt):.1%}",
            help="NGルールを除外し、次の工程へ引き継がれるメタデータ件数"
        )
        st.metric(
            "キーワード判別進捗", 
            f"全 {total_about_types:,} 語",
            delta=f"NG: {ng_classified_count} / OK: {ok_classified_count} / 未: {unclassified_count}",
            help="登録されたNG/OKキーワードの総種類数"
        )

        st.write("---")

        # 2. 仮選択の一括適用 ＆ 保存アクション
        st.markdown("##### ⚡ ルール確定 ＆ 保存")
        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]
        draft_count = len(draft_ab)

        if draft_count > 0:
            st.warning(f"現在 **{draft_count} 件** のキーワードが仮選択中です。")
            if st.button(f"⚡ 仮設定 ({draft_count} 件) を確定して保存", type="primary", use_container_width=True, key="btn_apply_cluster_draft_ctrl"):
                for kw, status in draft_ab.items():
                    if status == "NG":
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    elif status == "OK":
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    elif status == "RESET":
                        current_ng.discard(kw)
                        current_ok.discard(kw)
                draft_ab.clear()
                
                save_dict = {k: "NG" for k in current_ng}
                save_dict.update({k: "OK" for k in current_ok})
                safe_save_json(save_dict, about_rules_path)

                st.session_state["chk_view_ver"] += 1
                st.success("判別結果を確定し about_rules.json へ保存しました。")
                st.rerun()
        else:
            st.caption("✅ すべてのルールが保存済みです。クラスタやピルを選択すると確定ボタンが表示されます。")

        st.write("---")

        # 3. フィルタ適用実行
        st.markdown("##### 🚀 フィルタ適用実行")
        if st.button("About フィルタを実行する", type="primary", use_container_width=True, key="btn_run_about_filter_ctrl"):
            # 仮選択がある場合は自動コミット＆保存
            if len(draft_ab) > 0:
                for kw, status in draft_ab.items():
                    if status == "NG":
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    elif status == "OK":
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    elif status == "RESET":
                        current_ng.discard(kw)
                        current_ok.discard(kw)
                draft_ab.clear()

            save_dict = {k: "NG" for k in current_ng}
            save_dict.update({k: "OK" for k in current_ok})
            safe_save_json(save_dict, about_rules_path)

            data_dir = os.path.dirname(about_filtered_path)
            passed, disc = run_about_filter(input_path, about_rules_path, about_filtered_path, f"{data_dir}/discarded_about.csv")
            
            st.session_state["cluster_visible_limit"] = int(st.session_state.get("num_clusters_per_page", 10))
            st.session_state["chk_view_ver"] += 1
            st.success(f"About フィルタ完了: 通過 {passed:,} 件 / 除外 {disc:,} 件")
            st.rerun()

        st.write("---")

        # 4. 表示・操作オプション
        st.markdown("##### ⚙️ 表示・操作設定")
        
        def _on_tgl_hide_classified():
            st.session_state["persistent_hide_classified"] = st.session_state["chk_hide_classified_clusters"]
            
        def _on_tgl_hide_zero():
            st.session_state["persistent_hide_zero_pills"] = st.session_state["chk_hide_zero_cluster_pills"]

        hide_fully_classified = st.checkbox(
            "判定済みのクラスタおよびピルを非表示", 
            value=st.session_state["persistent_hide_classified"],
            key="chk_hide_classified_clusters", 
            on_change=_on_tgl_hide_classified,
            help="すでにOK/NG判定済みのクラスタおよびクラスタ内の判定済みピルを非表示にし、未判定項目のみに集中できます。"
        )
        hide_zero_cluster_pills = st.checkbox(
            "残存0件のピルを非表示", 
            value=st.session_state["persistent_hide_zero_pills"],
            key="chk_hide_zero_cluster_pills", 
            on_change=_on_tgl_hide_zero,
            help="他条件ですでに除外され、現在の残存件数が0件になったキーワードをクラスタ内から非表示にします。"
        )
        sort_cluster_by = st.selectbox("クラスタソート順:", ["残存データ件数順 (推奨)", "所属キーワード数順"], key="sb_cluster_sort")
        clusters_per_page = st.number_input("1回のクラスタ追加数", min_value=5, max_value=100, value=10, step=5, key="num_clusters_per_page")

        st.write("---")

        # 5. 初期化
        with st.popover("🗑️ ルール全初期化", help="Aboutルールを初期化"):
            st.warning("About ルール設定 (`about_rules.json`) を全初期化しますか？")
            st.caption("登録済みの NG / OK パターンがすべて消去されます。")
            if st.button("確定して初期化を実行", type="primary", use_container_width=True, key="btn_confirm_reset_about"):
                st.session_state["edited_noise"] = set()
                st.session_state["edited_strong"] = set()
                st.session_state["draft_about_changes"] = {}
                safe_save_json({}, about_rules_path)
                
                data_dir = os.path.dirname(about_filtered_path)
                for p_rm in [about_filtered_path, f"{data_dir}/discarded_about.csv"]:
                    if os.path.exists(p_rm):
                        try:
                            os.remove(p_rm)
                        except Exception:
                            pass
                st.cache_data.clear()
                st.session_state["chk_view_ver"] += 1
                st.success("About ルールおよびフィルタ適用結果を初期化しました。")
                st.rerun()

    # =========================================================================
    # 左側: メイン作業領域 (タブ群 ＆ 自動スクロールボード)
    # =========================================================================
    with col_main:
        def get_eff_status(kw):
            if kw in draft_ab:
                v = draft_ab[kw]
                return "OK" if v == "OK" else ("NG" if v == "NG" else "UN")
            if kw in current_ok:
                return "OK"
            if kw in current_ng:
                return "NG"
            return "UN"

        tab_cluster, tab_single, tab_custom, tab_llm, tab_manage = st.tabs([
            "🧩 クラスタ一括判別 (推奨)",
            "📊 単体キーワード判別ボード",
            "🎯 自由入力一括指定 (カスタム)",
            "🤖 LLMノイズ候補提案",
            f"📋 登録済ルール管理 ({len(current_ng)} NG / {len(current_ok)} OK)"
        ])

        # ---------------------------------------------------------------------
        # TAB 1: クラスタ一括判別 (推奨)
        # ---------------------------------------------------------------------
        with tab_cluster:
            st.markdown("類似性に基づいて抽出されたキーワード群に対し、一括/個別の判定（OK/NG/未判定）を行います。")

            def render_single_cluster_card(c, cid, kws):
                ng_c = sum(1 for k in kws if get_eff_status(k) == "NG")
                ok_c = sum(1 for k in kws if get_eff_status(k) == "OK")
                un_c = len(kws) - ng_c - ok_c

                if ng_c > 0 and ok_c == 0 and un_c == 0:
                    status_badge = "全除外 (NG)"
                elif ok_c > 0 and ng_c == 0 and un_c == 0:
                    status_badge = "全保持 (OK)"
                elif ok_c > 0 or ng_c > 0:
                    status_badge = f"混合 (OK:{ok_c} / NG:{ng_c} / 未:{un_c})"
                else:
                    status_badge = f"未判定 (全{un_c}件)"

                from components.ndc_utils import format_about_keyword_display

                # クラスタに属するユニークレコード件数および残存件数をO(1)集合演算で高速算出
                cl_doc_set = set()
                for k in kws:
                    cl_doc_set.update(kw_to_doc_indices.get(k, []))
                cl_total_cnt = len(cl_doc_set)
                cl_act_cnt = len(cl_doc_set & active_doc_indices)

                # ピルの絞り込み（判定済み非表示 ＆ 残存0件非表示オプション）
                # ★確定保存済みのピルのみ非表示にし、現在選択中の「仮設定ピル (kw in draft_ab)」は保存/確定まで表示を継続！
                visible_kws_info = []
                for kw in kws:
                    kw_indices = kw_to_doc_indices.get(kw, [])
                    eff_kw_cnt = sum(1 for idx in kw_indices if idx in active_doc_indices)
                    st_val = get_eff_status(kw)
                    is_in_draft = (kw in draft_ab)
                    
                    is_classified = (st_val in ("OK", "NG")) and not is_in_draft
                    is_zero_remaining = (eff_kw_cnt == 0) and not is_in_draft

                    if hide_fully_classified and is_classified:
                        continue
                    if hide_zero_cluster_pills and is_zero_remaining:
                        continue
                    visible_kws_info.append((kw, eff_kw_cnt, st_val, len(kw_indices), is_in_draft))

                # 表示すべきピルがなく、かつ仮設定もない場合はクラスタごと非表示
                has_draft = any(k in draft_ab for k in kws)
                if len(visible_kws_info) == 0 and not has_draft:
                    return

                kw_preview = ", ".join([format_about_keyword_display(k, 18) for k in kws[:4]]) + ("..." if len(kws) > 4 else "")
                expander_title = f"{c['name']} ➔ [{status_badge}] （対象語句: {kw_preview} [{len(kws)}種類] ｜ 残存: {cl_act_cnt:,} 件 / 総 {cl_total_cnt:,} 件）"

                with st.expander(expander_title, expanded=True):
                    # 一括操作の対象キーワード選定（既存のOK/NG判定を保護）
                    unclassified_kws = [k for k in kws if get_eff_status(k) == "UN"]
                    is_partial = len(unclassified_kws) < len(kws)
                    target_batch_kws = unclassified_kws if (is_partial or hide_fully_classified) else kws

                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        btn_ok_label = f"未判定のみ一括 OK [{len(target_batch_kws)}件]" if is_partial else f"一括 OK 仮設定 [{len(kws)}件]"
                        if st.button(btn_ok_label, key=f"btn_cl_ok_{cid}", type="secondary", use_container_width=True, disabled=(len(target_batch_kws) == 0)):
                            for k in target_batch_kws:
                                draft_ab[k] = "OK"
                            st.rerun()
                    with b_col2:
                        btn_ng_label = f"未判定のみ一括 NG [{len(target_batch_kws)}件]" if is_partial else f"一括 NG 仮設定 [{len(kws)}件]"
                        if st.button(btn_ng_label, key=f"btn_cl_ng_{cid}", type="primary", use_container_width=True, disabled=(len(target_batch_kws) == 0)):
                            for k in target_batch_kws:
                                draft_ab[k] = "NG"
                            st.rerun()
                    with b_col3:
                        if st.button(f"一括 未判定リセット", key=f"btn_cl_reset_{cid}", use_container_width=True):
                            for k in kws:
                                draft_ab[k] = "RESET"
                            st.rerun()

                    if not visible_kws_info:
                        if un_c == 0:
                            st.caption("※ このクラスタ内のキーワードはすべて判定済みのため非表示になっています。")
                        else:
                            st.caption("※ このクラスタ内の未判定キーワードはすべて他条件で除外済み（残存0件）のため非表示になっています。")
                    else:
                        hidden_count = len(kws) - len(visible_kws_info)
                        cur_m_name = st.session_state.get("click_action_about_mode", "NGに設定")
                        st.caption(f"個別判定 (クリックで『{cur_m_name}』、右側パネルで切替可能):" + (f" [非表示: {hidden_count} 件]" if hidden_count > 0 else ""))
                        
                        # 1クラスタあたりの描画上限（最大24件、展開可能）
                        cl_limit_key = f"cl_kws_limit_{cid}"
                        cur_kw_limit = st.session_state.get(cl_limit_key, 24)
                        display_kws_info = visible_kws_info[:cur_kw_limit]

                        cl_cols = st.columns(3)
                        for idx_k, (kw, eff_kw_cnt, st_val, tot_kw_cnt, is_in_draft) in enumerate(display_kws_info):
                            col_k = cl_cols[idx_k % 3]
                            disp_k = format_about_keyword_display(kw, max_label_len=24)
                            
                            cnt_badge = f" ({eff_kw_cnt:,}件)" if eff_kw_cnt != tot_kw_cnt else f" ({tot_kw_cnt:,}件)"
                            draft_tag = " [仮]" if is_in_draft else ""
                            if st_val == "OK":
                                lbl = f"✅{draft_tag} {disp_k}{cnt_badge}"
                            elif st_val == "NG":
                                lbl = f"🚫{draft_tag} {disp_k}{cnt_badge}"
                            else:
                                lbl = f"❓{draft_tag} {disp_k}{cnt_badge}"

                            c_btn_k, c_pop_k = col_k.columns([5, 1])
                            with c_btn_k:
                                if st.button(lbl, key=f"tgl_kw_{cid}_{kw}", use_container_width=True):
                                    cur_m = st.session_state.get("click_action_about_mode", "NGに設定")
                                    if cur_m == "NGに設定":
                                        draft_ab[kw] = "NG"
                                    elif cur_m == "OKに設定":
                                        draft_ab[kw] = "OK"
                                    elif cur_m == "未判定に戻す":
                                        draft_ab[kw] = "RESET"
                                    else:
                                        if st_val == "OK":
                                            draft_ab[kw] = "NG"
                                        elif st_val == "NG":
                                            draft_ab[kw] = "RESET"
                                        else:
                                            draft_ab[kw] = "OK"
                                    st.rerun()
                            with c_pop_k:
                                with st.popover("🔍", help=f"『{disp_k}』の外部検索・該当資料詳細"):
                                    st.markdown(f"### 🔍 『{format_about_keyword_display(kw)}』")
                                    st.markdown(make_rich_search_links_md(kw))
                                    st.markdown(f"- 該当資料件数: **未除外残存: {eff_kw_cnt:,} 件** （初期メタデータセット全体: {tot_kw_cnt:,} 件）")
                                    kw_indices = kw_to_doc_indices.get(kw, [])
                                    if kw_indices:
                                        st.write("---")
                                        st.caption(f"📄 **該当資料一覧 (アクティブ残存資料を優先表示、上位15件)**:")
                                        
                                        sorted_kw_indices = sorted(kw_indices, key=lambda i: 0 if i in active_doc_indices else 1)
                                        sample_lines = []
                                        from components.file_utils import make_jps_item_url
                                        for idx_doc in sorted_kw_indices[:15]:
                                            rec = raw_records[idx_doc]
                                            r_title = rec.get('title', '') or "（無題）"
                                            r_id = rec.get('id', '')
                                            creator_part = f" （著者: `{rec.get('creator')}`）" if rec.get('creator') else ""
                                            is_act = idx_doc in active_doc_indices
                                            tag = "" if is_act else " <span style='color: #ff6b6b; font-size: 0.8rem;'>[🚫他条件で除外済]</span>"
                                            item_link = make_jps_item_url(r_id, r_title)
                                            sample_lines.append(f"• [📖 **{r_title}**]({item_link}){creator_part}{tag}")
                                        
                                        if len(sorted_kw_indices) > 15:
                                            sample_lines.append(f"\n*※ 他 {len(sorted_kw_indices) - 15:,} 件の資料があります（上位15件を表示中）*")
                                            
                                        with st.container(height=280):
                                            st.markdown("\n".join(sample_lines), unsafe_allow_html=True)

                        if len(visible_kws_info) > cur_kw_limit:
                            rem_kw_cnt = len(visible_kws_info) - cur_kw_limit
                            if st.button(f"➕ クラスタ内の残りのキーワード ({rem_kw_cnt}件) をすべて表示", key=f"btn_more_kws_{cid}", use_container_width=True):
                                st.session_state[cl_limit_key] = len(visible_kws_info)
                                st.rerun()

                    # クラスタ内に仮設定がある場合はカード内にも即時確定保存ボタンを表示
                    cluster_draft_kws = [k for k in kws if k in draft_ab]
                    if cluster_draft_kws:
                        st.write("---")
                        c_save_col1, c_save_col2 = st.columns([3, 2])
                        with c_save_col1:
                            st.info(f"📌 このクラスタ内に **{len(cluster_draft_kws)} 件** の仮設定があります。")
                        with c_save_col2:
                            if st.button(f"⚡ このクラスタを確定保存 ({len(cluster_draft_kws)}件)", key=f"btn_save_cl_card_{cid}", type="primary", use_container_width=True):
                                for kw in cluster_draft_kws:
                                    status = draft_ab[kw]
                                    if status == "NG":
                                        current_ng.add(kw)
                                        current_ok.discard(kw)
                                    elif status == "OK":
                                        current_ok.add(kw)
                                        current_ng.discard(kw)
                                    elif status == "RESET":
                                        current_ng.discard(kw)
                                        current_ok.discard(kw)
                                    del draft_ab[kw]

                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)

                                st.session_state["chk_view_ver"] += 1
                                st.success(f"クラスタ『{c['name']}』のルールを確定保存しました。")
                                st.rerun()

            # 各キーワードのアクティブ残存件数を一括事前計算 (O(N))
            kw_eff_counts_map = {}
            for kw, indices in kw_to_doc_indices.items():
                kw_eff_counts_map[kw] = sum(1 for idx in indices if idx in active_doc_indices)

            def render_cluster_board():
                display_clusters = []
                for c in about_clusters:
                    kws = c["keywords"]
                    
                    # 各キーワードのアクティブ残存状況と表示対象判定
                    cluster_visible_kws = []
                    has_draft_in_cluster = False
                    ng_c = 0
                    ok_c = 0
                    un_c = 0
                    
                    for k in kws:
                        is_in_draft = (k in draft_ab)
                        if is_in_draft:
                            has_draft_in_cluster = True
                        
                        eff_k_cnt = kw_eff_counts_map.get(k, 0)
                        st_val = get_eff_status(k)
                        if st_val == "NG":
                            ng_c += 1
                        elif st_val == "OK":
                            ok_c += 1
                        else:
                            un_c += 1
                        
                        is_classified = (st_val in ("OK", "NG")) and not is_in_draft
                        is_zero_remaining = (eff_k_cnt == 0) and not is_in_draft
                        
                        if hide_fully_classified and is_classified:
                            continue
                        if hide_zero_cluster_pills and is_zero_remaining:
                            continue
                            
                        cluster_visible_kws.append(k)

                    # 表示すべきピルが1つもなく、かつ仮選択もないクラスタは一覧から除外
                    if len(cluster_visible_kws) == 0 and not has_draft_in_cluster:
                        continue

                    # クラスタのユニーク残存件数を計算
                    cl_doc_set = set()
                    for k in kws:
                        cl_doc_set.update(kw_to_doc_indices.get(k, []))
                    cl_act_cnt = len(cl_doc_set & active_doc_indices)
                    cl_tot_cnt = len(cl_doc_set)

                    if hide_zero_cluster_pills and cl_act_cnt == 0 and not has_draft_in_cluster:
                        continue

                    display_clusters.append({
                        **c,
                        "ng_count": ng_c,
                        "ok_count": ok_c,
                        "un_count": un_c,
                        "active_count": cl_act_cnt,
                        "unique_total_count": cl_tot_cnt,
                        "visible_kws_count": len(cluster_visible_kws)
                    })

                if sort_cluster_by == "所属キーワード数順":
                    display_clusters.sort(key=lambda x: len(x["keywords"]), reverse=True)
                else:
                    display_clusters.sort(key=lambda x: x["active_count"], reverse=True)

                total_display_clusters = len(display_clusters)

                if total_display_clusters == 0:
                    st.success("表示条件に一致する未判定のクラスタはありません。")
                    return

                if "cluster_visible_limit" not in st.session_state:
                    st.session_state["cluster_visible_limit"] = int(clusters_per_page)

                cur_cl_limit = min(total_display_clusters, max(int(clusters_per_page), int(st.session_state.get("cluster_visible_limit", clusters_per_page))))
                st.session_state["cluster_visible_limit"] = cur_cl_limit

                st.markdown(f"<div style='padding: 4px 0 8px 0;'><b>全 {total_display_clusters} クラスタ中 {cur_cl_limit} クラスタを表示中</b></div>", unsafe_allow_html=True)

                page_clusters = display_clusters[:cur_cl_limit]

                st.write("---")

                for c in page_clusters:
                    render_single_cluster_card(c, c["cluster_id"], c["keywords"])

                # ボトムの追加読み込み
                if cur_cl_limit < total_display_clusters:
                    st.write("---")
                    btn_cl_txt = f"🔽 次の {int(clusters_per_page)} クラスタを読み込む (現在 {cur_cl_limit} / 全 {total_display_clusters} クラスタ)"
                    if st.button(btn_cl_txt, key="btn_bot_more_clusters", type="secondary", use_container_width=True):
                        st.session_state["cluster_visible_limit"] = min(total_display_clusters, cur_cl_limit + int(clusters_per_page))
                        st.rerun()
                else:
                    st.caption(f"✅ 全 {total_display_clusters} クラスタを表示完了しました。")

            render_cluster_board()

    with tab_single:
        col_opt1, col_opt2 = st.columns([3, 2])
        with col_opt1:
            view_filter_mode = st.radio(
                "表示オプション:", 
                options=["すべて表示", "未判定のみ", "NGのみ", "OKのみ"], 
                horizontal=True,
                key="view_filter_about_mode"
            )
            is_unclassified_mode = (view_filter_mode == "未判定のみ")
            hide_zero_about = st.checkbox(
                "残存未判定件数が 0 件のキーワードを非表示にする", 
                value=True, 
                key="chk_hide_zero_about"
            )
        with col_opt2:
            search_query = st.text_input("キーワード検索:", placeholder="例: 演劇 -能", key="q_about_pills")

        if "click_action_about_mode" not in st.session_state:
            st.session_state["click_action_about_mode"] = "NGに設定"

        st.caption("判定モード切替 (ショートカット: Q / W / E キー):")
        c_m1, c_m2, c_m3 = st.columns(3)
        
        btn1_type = "primary" if st.session_state["click_action_about_mode"] == "NGに設定" else "secondary"
        btn2_type = "primary" if st.session_state["click_action_about_mode"] == "OKに設定" else "secondary"
        btn3_type = "primary" if st.session_state["click_action_about_mode"] == "未判定に戻す" else "secondary"

        b1 = c_m1.button("【 Q 】 NG設定モード", key="btn_shortcut_ab_q", type=btn1_type, use_container_width=True)
        b2 = c_m2.button("【 W 】 OK設定モード", key="btn_shortcut_ab_w", type=btn2_type, use_container_width=True)
        b3 = c_m3.button("【 E 】 未判定リセット", key="btn_shortcut_ab_e", type=btn3_type, use_container_width=True)

        if hotkeys:
            if hotkeys.pressed("mode_ng"):
                st.session_state["click_action_about_mode"] = "NGに設定"
                st.rerun()
            elif hotkeys.pressed("mode_ok"):
                st.session_state["click_action_about_mode"] = "OKに設定"
                st.rerun()
            elif hotkeys.pressed("mode_reset"):
                st.session_state["click_action_about_mode"] = "未判定に戻す"
                st.rerun()

        if b1:
            st.session_state["click_action_about_mode"] = "NGに設定"
            st.rerun()
        if b2:
            st.session_state["click_action_about_mode"] = "OKに設定"
            st.rerun()
        if b3:
            st.session_state["click_action_about_mode"] = "未判定に戻す"
            st.rerun()

        click_action_mode = st.session_state["click_action_about_mode"]

        if click_action_mode == "NGに設定":
            st.error("【現在の設定モード: NG (除外)】 (ショートカット: Q)")
        elif click_action_mode == "OKに設定":
            st.success("【現在の設定モード: OK (保持)】 (ショートカット: W)")
        elif click_action_mode == "未判定に戻す":
            st.info("【現在の設定モード: 未判定リセット】 (ショートカット: E)")

        filtered_ranking = about_ranking
        if view_filter_mode == "未判定のみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k not in current_ng and k not in current_ok]
        elif view_filter_mode == "NGのみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ng]
        elif view_filter_mode == "OKのみ":
            filtered_ranking = [(k, c) for k, c in filtered_ranking if k in current_ok]

        if search_query:
            from components.ndc_utils import format_about_keyword_display
            parts = [p.strip() for p in re.split(r'\s+', search_query.replace('　', ' ')) if p.strip()]
            inc_words = [p.lower() for p in parts if not p.startswith('-')]
            exc_words = [p[1:].lower() for p in parts if p.startswith('-') and len(p) > 1]
            
            res_list = []
            for kw, cnt in filtered_ranking:
                kw_l = kw.lower()
                disp_kw_l = format_about_keyword_display(kw).lower()
                if all(i in kw_l or i in disp_kw_l for i in inc_words) and not any(e in kw_l or e in disp_kw_l for e in exc_words):
                    res_list.append((kw, cnt))
            filtered_ranking = res_list
        # 残存未判定件数 (eff_cnt) の超高速算出 (整数カウントのみ)
        kw_eff_counts = {}
        for kw, cnt in filtered_ranking:
            doc_idx_list = kw_to_doc_indices.get(kw, [])
            eff_c = sum(1 for idx in doc_idx_list if idx in active_doc_indices)
            kw_eff_counts[kw] = eff_c

        if hide_zero_about:
            filtered_ranking = [
                (kw, cnt) for kw, cnt in filtered_ranking 
                if kw_eff_counts.get(kw, 0) > 0 or kw in current_ng or kw in current_ok
            ]

        class LazySamplesMap(dict):
            def __init__(self, kw_to_doc_indices, active_doc_indices, raw_records, kw_eff_counts):
                self.kw_to_doc_indices = kw_to_doc_indices
                self.active_doc_indices = active_doc_indices
                self.raw_records = raw_records
                self.kw_eff_counts = kw_eff_counts

            def get(self, kw, default=None):
                eff_c = self.kw_eff_counts.get(kw, 0)
                doc_idx_list = self.kw_to_doc_indices.get(kw, [])
                act_indices = [idx for idx in doc_idx_list if idx in self.active_doc_indices]
                samples_list = []
                for i in act_indices[:10]:
                    rec = self.raw_records[i]
                    samples_list.append({
                        "id": rec.get("id", ""),
                        "title": rec.get("title", ""),
                        "desc": rec.get("desc", ""),
                        "creator": rec.get("creator", "")
                    })
                return {
                    "eff_cnt": eff_c,
                    "samples": samples_list
                }
        
        active_samples_info = LazySamplesMap(kw_to_doc_indices, active_doc_indices, raw_records, kw_eff_counts)

        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]

        # 汎用ピルボードコンポーネント呼出
        render_pill_board(
            items=filtered_ranking,
            active_samples_map=active_samples_info,
            current_ng=current_ng,
            current_ok=current_ok,
            draft_dict=draft_ab,
            click_action_mode=click_action_mode,
            page_session_key="about_single_page"
        )

        c_hdr1, c_hdr2 = st.columns([3, 2])
        with c_hdr1:
            st.markdown(f"判定対象キーワード (該当: **{len(filtered_ranking)}** 件)")
        with c_hdr2:
            draft_count = len(draft_ab)
            btn_apply_label = f"仮設定 ({draft_count} 件) の一括適用" if draft_count > 0 else "判定の一括適用"
            if st.button(btn_apply_label, type="primary" if draft_count > 0 else "secondary", use_container_width=True, key="btn_single_draft_apply"):
                if draft_ab:
                    for kw, status in draft_ab.items():
                        if status == "NG":
                            current_ng.add(kw)
                            current_ok.discard(kw)
                        elif status == "OK":
                            current_ok.add(kw)
                            current_ng.discard(kw)
                        elif status == "RESET":
                            current_ng.discard(kw)
                            current_ok.discard(kw)
                    draft_ab.clear()
                    
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)

                    st.session_state["chk_view_ver"] += 1
                    st.success("仮判定をルールへ一括適用しました。")
                    st.rerun()
                else:
                    st.info("現在仮選択中のキーワードはありません。")

    # -------------------------------------------------------------------------
    # TAB 3: 自由入力キーワード一括指定 (カスタム指定)
    # -------------------------------------------------------------------------
    with tab_custom:
        st.markdown("### 自由入力による主題(About)キーワード除外・保持指定")
        st.caption("主題（schema:about）に含まれる特定の語句（例: `工芸, 建築, 絵画, 彫刻, 陶芸, 写真, 考古学` など）を入力し、ヒットする資料を確認しながら一括除外・保持指定できます。")

        if "about_custom_txt_ver" not in st.session_state:
            st.session_state["about_custom_txt_ver"] = 0
        txt_ver_ab = st.session_state["about_custom_txt_ver"]
        txt_key_ab = f"txt_custom_about_kws_{txt_ver_ab}"

        custom_about_input = st.text_area(
            "除外・保持したい主題キーワード (カンマ、読点、または改行区切りで複数入力可能):",
            placeholder="例: 工芸, 建築, 絵画, 彫刻, 陶芸, 写真, 考古学",
            height=80,
            key=txt_key_ab
        )

        parsed_custom_ab = [
            w.strip() for w in re.split(r"[\n,、・/／\s]+", custom_about_input) if len(w.strip()) >= 1
        ]
        parsed_custom_ab = list(dict.fromkeys(parsed_custom_ab))

        if parsed_custom_ab:
            st.markdown(f"#### 🔍 入力された {len(parsed_custom_ab)} 件のキーワードのヒット検証")
            
            ab_hit_stats = []
            total_impact_docs = set()
            active_impact_docs = set()

            for kw in parsed_custom_ab:
                doc_indices = kw_to_doc_indices.get(kw, [])
                act_indices = [idx for idx in doc_indices if idx in active_doc_indices]
                
                total_impact_docs.update(doc_indices)
                active_impact_docs.update(act_indices)
                
                is_currently_ng = kw in current_ng
                is_currently_ok = kw in current_ok
                
                ab_hit_stats.append({
                    "keyword": kw,
                    "total_hits": len(doc_indices),
                    "active_hits": len(act_indices),
                    "doc_indices": doc_indices[:15],
                    "status": "NG" if is_currently_ng else ("OK" if is_currently_ok else "未登録")
                })

            c_s1, c_s2, c_s3 = st.columns(3)
            with c_s1:
                st.metric("指定キーワード総数", f"{len(parsed_custom_ab)} 語")
            with c_s2:
                st.metric("ヒットする資料総数", f"{len(total_impact_docs):,} 件", help="初期メタデータセット全体でいずれかのキーワードが付与された資料数")
            with c_s3:
                st.metric("新規除外インパクト", f"{len(active_impact_docs):,} 件", delta=f"-{len(active_impact_docs):,} 件", delta_color="inverse", help="現在まだ除外されていないデータから新たに削ぎ落とされる件数")

            c_a1, c_a2, c_a3 = st.columns([2, 2, 1])
            with c_a1:
                if st.button(f"🚫 指定した {len(parsed_custom_ab)} 語を一括で NG (除外) ルールへ追加", type="primary", use_container_width=True, key="btn_apply_about_custom_ng"):
                    for kw in parsed_custom_ab:
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_ab)} 件のキーワードを NG ルールへ登録しました。")
                    st.rerun()

            with c_a2:
                if st.button(f"✅ 指定した {len(parsed_custom_ab)} 語を一括で OK (保持) ルールへ追加", type="secondary", use_container_width=True, key="btn_apply_about_custom_ok"):
                    for kw in parsed_custom_ab:
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_ab)} 件のキーワードを OK ルールへ登録しました。")
                    st.rerun()

            with c_a3:
                if st.button("🔄 入力クリア", use_container_width=True, key="btn_clear_about_custom_input"):
                    st.session_state["about_custom_txt_ver"] += 1
                    st.rerun()

            st.write("---")
            st.markdown("##### 📋 キーワード別ヒット詳細 ＆ 該当資料例")
            for stat in ab_hit_stats:
                kw = stat["keyword"]
                tot_h = stat["total_hits"]
                act_h = stat["active_hits"]
                cur_st = stat["status"]
                
                if cur_st == "NG":
                    st_badge = "🚫 [NG登録済]"
                elif cur_st == "OK":
                    st_badge = "✅ [OK登録済]"
                else:
                    st_badge = "❓ [未登録]"

                exp_header = f"『{kw}』 ➔ 全 {tot_h:,} 件ヒット (未判定: {act_h:,} 件) ｜ {st_badge}"
                with st.expander(exp_header, expanded=(tot_h > 0 and cur_st == "未登録")):
                    c_k1, c_k2 = st.columns([3, 1])
                    with c_k1:
                        st.markdown(make_rich_search_links_md(kw))
                    with c_k2:
                        if cur_st != "NG":
                            if st.button(f"🚫 『{kw}』をNGに登録", key=f"btn_cust_ab_ng_{kw}", use_container_width=True):
                                current_ng.add(kw)
                                current_ok.discard(kw)
                                save_dict = {}
                                for k in current_ng: save_dict[k] = "NG"
                                for k in current_ok: save_dict[k] = "OK"
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            if st.button(f"↩️ 『{kw}』をNG解除", key=f"btn_cust_ab_del_{kw}", use_container_width=True):
                                current_ng.discard(kw)
                                save_dict = {}
                                for k in current_ng: save_dict[k] = "NG"
                                for k in current_ok: save_dict[k] = "OK"
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()

                    st.caption(f"該当する資料の具体例 (先頭 {len(stat['doc_indices'])} 件):")
                    from components.file_utils import make_jps_item_url
                    for idx_doc in stat["doc_indices"]:
                        rec = raw_records[idx_doc]
                        r_title = rec.get('title', '') or "（無題）"
                        r_id = rec.get('id', '')
                        creator_part = f" ({rec.get('creator')})" if rec.get('creator') else ""
                        item_link = make_jps_item_url(r_id, r_title)
                        st.markdown(f"• [📖 **{r_title}**]({item_link}){creator_part}")
        else:
            st.info("上記テキストエリアに除外したい主題単語（例: `工芸, 建築, 絵画, 彫刻, 陶芸, 写真`）を入力すると、一致する資料の検出と一括除外が行えます。")

    # -------------------------------------------------------------------------
    # TAB 4: LLMノイズ候補提案
    # -------------------------------------------------------------------------
    with tab_llm:
        st.markdown("【全域ノイズ判定アシスト】: 保持したいドメイン中心語を指定し、データセット全体から対象外キーワードの候補をLLMで自動抽出します。")
        default_targets = list(current_ok) if current_ok else st.session_state.get("expansion_res", {}).get("keywords", ["楽譜", "音楽", "音譜", "能楽", "三味線"])
        target_input = st.text_input("保持対象 (ターゲット) キーワード (カンマ区切り):", value=", ".join(default_targets), key="txt_target_kws_tab")

        c_top1, c_top2 = st.columns([3, 1])
        with c_top1:
            st.caption("抽出されたノイズ候補を選択し、一括で NG リストへ登録できます。")
        with c_top2:
            if st.button("LLMによるノイズ候補の提案", type="primary", use_container_width=True, key="btn_suggest_llm_ng"):
                sample_kws = [k for k, c in about_ranking[:60]]
                domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の文化資源・資料")
                target_kws_list = [t.strip() for t in target_input.split(",") if t.strip()]

                with st.spinner("LLMがデータセット全体から対象外キーワードを抽出中..."):
                    cfg = st.session_state.get("llm_config", {})
                    suggs = suggest_ng_keywords_with_llm(
                        current_ng_list=list(current_ng), 
                        sample_keywords=sample_kws, 
                        target_keywords=target_kws_list,
                        domain_definition=domain_def,
                        provider=cfg.get("provider", "local"),
                        api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                        api_key=cfg.get("api_key", ""),
                        model=cfg.get("model", "local-model")
                    )
                    st.session_state["llm_about_suggs"] = suggs

        if "llm_about_suggs" in st.session_state:
            suggs = st.session_state["llm_about_suggs"]
            if suggs:
                st.warning(f"🤖 LLMが抽出したノイズ候補 (全 {len(suggs)} 件)")
                selected_suggs = st.multiselect("一括登録するキーワードの選択:", options=suggs, default=suggs, key="ms_llm_suggs")
                if st.button("選択したノイズ候補を NG リストに追加", type="primary", key="btn_add_llm_suggs_ng"):
                    if selected_suggs:
                        current_ng.update(selected_suggs)
                        st.success(f"{len(selected_suggs)} 件を NG リストに追加しました。")
                        st.session_state.pop("llm_about_suggs", None)
                        st.rerun()
        # -------------------------------------------------------------------------
        # TAB 5: 登録済ルール管理
        # -------------------------------------------------------------------------
        with tab_manage:
            from components.ndc_utils import format_about_keyword_display
            st.markdown(f"現在登録されている About 判定ルールの一覧です（**NG: {len(current_ng)} 件** ｜ **OK: {len(current_ok)} 件**）。")
            
            c_mng1, c_mng2 = st.columns(2)
            with c_mng1:
                st.markdown(f"##### 🚫 登録済 NG (除外) ルール [{len(current_ng)} 件]")
                if current_ng:
                    ng_sorted = sorted(list(current_ng))
                    for kw in ng_sorted:
                        disp_k = format_about_keyword_display(kw)
                        c_w, c_del = st.columns([5, 1])
                        with c_w:
                            st.markdown(f"• **{disp_k}**")
                        with c_del:
                            if st.button("🗑️ 削除", key=f"del_mng_ng_{kw}", use_container_width=True):
                                current_ng.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.rerun()
                else:
                    st.info("登録済みの NG ルールはありません。")

            with c_mng2:
                st.markdown(f"##### ✅ 登録済 OK (保持) ルール [{len(current_ok)} 件]")
                if current_ok:
                    ok_sorted = sorted(list(current_ok))
                    for kw in ok_sorted:
                        disp_k = format_about_keyword_display(kw)
                        c_w, c_del = st.columns([5, 1])
                        with c_w:
                            st.markdown(f"• **{disp_k}**")
                        with c_del:
                            if st.button("🗑️ 削除", key=f"del_mng_ok_{kw}", use_container_width=True):
                                current_ok.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.rerun()
                else:
                    st.info("登録済みの OK ルールはありません。")



