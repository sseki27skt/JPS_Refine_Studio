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
from components.guide_card import render_guide_card, render_summary_banner, render_step_navigation
from modules.rule_filter import (
    run_about_filter,
    suggest_ng_keywords_with_llm,
    extract_about_keywords_from_jsonl,
    extract_about_values
)

try:
    from modules.duckdb_manager import DuckDBManager, get_duckdb_manager
except (ImportError, ValueError):
    try:
        from duckdb_manager import DuckDBManager, get_duckdb_manager
    except ImportError:
        DuckDBManager = None
        get_duckdb_manager = None

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
        extract_ndlc_code,
        resolve_ndlc_label,
        format_about_keyword_display,
        prefetch_about_keywords_batch,
        extract_ndlna_id, 
        resolve_ndlna_label
    )

    # 上位キーワードを事前一括解決（SPARQL 1.1 / NDC API）
    prefetch_about_keywords_batch([kw for kw, _ in about_ranking_tuples[:200]])

    ndc_groups = defaultdict(list)
    ndlc_groups = defaultdict(list)
    ndlna_items = []
    prefix_groups = defaultdict(list)
    unassigned = []

    # 1. NDCコード / NDLCコード / NDLNA典拠 / 階層区切り文字による分類
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

        # C. NDLCコードの判定
        ndlc_code = extract_ndlc_code(kw)
        if ndlc_code:
            ndlc_groups[ndlc_code].append((kw, count))
            continue

        # D. 階層区切り文字（--, /, :, _, ･, 空白）
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
            "name": f"NDC分類: {base_ndc}{tag_lbl}",
            "keywords": [k for k, c in items_sorted],
            "total_count": total_cnt
        })
        cluster_idx += 1

    # 3. NDLC分類クラスタの生成 (SPARQL APIに基づくラベル付与)
    for ndlc_c, items in ndlc_groups.items():
        items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
        total_cnt = sum(c for k, c in items_sorted)
        lbl_str = resolve_ndlc_label(ndlc_c)
        tag_lbl = f" [{lbl_str}]" if lbl_str else ""
        clusters.append({
            "cluster_id": f"cl_ndlc_{cluster_idx}",
            "name": f"NDLC分類: {ndlc_c}{tag_lbl}",
            "keywords": [k for k, c in items_sorted],
            "total_count": total_cnt
        })
        cluster_idx += 1

    # 4. NDL 典拠クラスタの生成 (NDLSH 件名 / NDLNA 人名・団体名)
    if ndlna_items:
        # 典拠クラスタに含まれる全キーワードを一括事前解決（SPARQL 1.1）
        auth_kws = [k for k, _ in ndlna_items]
        prefetch_about_keywords_batch(auth_kws, max_items=len(auth_kws))

        items_sorted = sorted(ndlna_items, key=lambda x: x[1], reverse=True)
        total_cnt = sum(c for k, c in items_sorted)
        # 代表ラベルのプレビュー
        top_labels = []
        for kw_item, _ in items_sorted[:3]:
            lbl = resolve_ndlna_label(extract_ndlna_id(kw_item))
            if lbl:
                top_labels.append(lbl)
        sub_desc = f" ({', '.join(top_labels)} 等)" if top_labels else ""
        clusters.append({
            "cluster_id": f"cl_ndlna_{cluster_idx}",
            "name": f"NDL典拠（件名・人名・団体名）{sub_desc}",
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
    st.markdown("取得データに含まれる `schema:about` キーワード（NDC分類、NDLNA典拠、件名）を解析し、除外対象（NG）および合格確定（OK: LLMスキップ）の判定を行います。")

    render_guide_card(
        step_num="Step 2-B",
        step_title="主題 (schema:about) キーワード分析・判別",
        purpose="NDC分類記号やNDLNA主題キーワードに基づき、確実な適合資料（合格）と明らかな無関係資料（除外）を高速判定します。",
        impact="判定が確定したレコードは後続のLLM推論をスキップし、判定保留（Grey）群のみが次へ渡されます。",
        condition="判定したい主題キーワードのルール（合格/除外）を設定・確定すること。"
    )

    raw_metadata_path = paths['PATH_RAW_METADATA']
    about_rules_path = paths['PATH_ABOUT_RULES']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    ngram_rules_path = paths.get('PATH_NGRAM_RULES', '01_cleansing_studio/rules/ngram_rules.json')
    ngram_filtered_path = paths.get('PATH_NGRAM_FILTERED', 'data/ngram_filtered.jsonl')

    if not os.path.exists(raw_metadata_path):
        st.warning("先に Step 1 で初期メタデータセット (raw_metadata.jsonl) を取得してください。")
        st.stop()

    duckdb_path = paths.get('PATH_DUCKDB', os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
    # DuckDBが存在し、type_filtered.jsonlが未生成の場合はDuckDBから高速自動同期 (1〜2秒)
    if os.path.exists(duckdb_path) and not os.path.exists(type_filtered_path) and DuckDBManager is not None:
        try:
            db = DuckDBManager(db_path=duckdb_path)
            db.export_type_filtered_jsonl(type_filtered_path)
            db.close()
        except Exception:
            pass

    # --- 入力データソースの選択 ＆ 前段/後段 相互連携コントロール ---
    data_source_options = []
    if os.path.exists(type_filtered_path):
        data_source_options.append("Step 2-A (データ種別) 適用後データ (type_filtered.jsonl)")
    if os.path.exists(ngram_filtered_path):
        data_source_options.append("Step 2-C (タイトル文字列) 適用後データ (ngram_filtered.jsonl)")
    data_source_options.append("初期メタデータセット全件 (raw_metadata.jsonl)")

    c_src1, c_src2 = st.columns([3, 2])
    with c_src1:
        chosen_source = st.selectbox(
            "分析対象データソース:",
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

    # Step 2-C タイトル NG ルールのロード (双方向完全自動連動用)
    has_ngram_rules = os.path.exists(ngram_rules_path)
    ngram_ng_set = set()
    if has_ngram_rules:
        try:
            with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                ng_r = json.load(f)
                ngram_ng_set = set([k for k, v in ng_r.items() if v == "NG"])
        except Exception:
            ngram_ng_set = set()

    with c_src2:
        link_ngram_rules = False
        if len(ngram_ng_set) > 0 and "ngram_filtered" not in chosen_source:
            link_ngram_rules = st.toggle(
                "🔗 Step 2-C (タイトルNGルール) を双方向自動連動",
                value=True,
                help="Step 2-C で確定登録済みのタイトル除外ルールに一致する資料を、Step 2-B の分析上でも自動的に除外扱いにして残存件数を計算します。OFFにすると2-A直後の素のデータで分析できます。",
                key="tgl_step2a_link_ngram"
            )
            if link_ngram_rules:
                st.caption(f"※ Step 2-C の登録ルール ({len(ngram_ng_set):,} 語) を自動反映中")
            else:
                st.caption("※ Step 2-C 連動を一時解除中 (2-A 直後の状態で分析)")
        elif "ngram_filtered" in chosen_source:
            st.success("Step 2-C の除外結果を反映したデータセットで分析中")

    use_duckdb = bool(os.path.exists(duckdb_path) and DuckDBManager is not None)
    exclude_ng_types = ("type_filtered" in chosen_source or chosen_source == data_source_options[0])

    @st.cache_data(show_spinner="DuckDBから主題キーワードを集計中...")
    def load_about_features(db_p, in_p, mtime, exclude_types):
        if db_p and os.path.exists(db_p) and DuckDBManager is not None:
            try:
                db = get_duckdb_manager(db_p) if get_duckdb_manager else DuckDBManager(db_path=db_p)
                ranking = db.get_about_keyword_counts(limit=3000, exclude_ng_types=exclude_types)
                tot_cnt = db.get_active_record_count(exclude_ng_types=exclude_types)
                if ranking:
                    return ranking, tot_cnt
            except Exception:
                pass
        
        # フォールバック (DuckDB不在時またはJSONL直接読み込み)
        ranking = extract_about_keywords_from_jsonl(in_p)
        tot_cnt = 0
        if os.path.exists(in_p):
            with open(in_p, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in f:
                    tot_cnt += 1
        return ranking, tot_cnt

    about_ranking, total_records_cnt = load_about_features(duckdb_path, input_path, input_mtime, exclude_ng_types)
    about_counts_map = dict(about_ranking)

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

    # フィルタフラグの永続セッション保持（デフォルトで残存0件を非表示にし、無駄な検討を排除）
    if "persistent_hide_classified" not in st.session_state:
        st.session_state["persistent_hide_classified"] = False
    if "persistent_hide_zero_pills" not in st.session_state:
        st.session_state["persistent_hide_zero_pills"] = True

    checked_words = st.session_state["checked_words"]

    # レコード（メタデータ件数）ベースの超高速シミュレーション
    total_about_types = len(about_ranking)
    
    # 確定済みルール + 現在の仮設定ルールを統合してリアルタイム計算
    draft_ng = set(k for k, v in draft_ab.items() if v == "NG")
    draft_ok = set(k for k, v in draft_ab.items() if v == "OK")
    draft_reset = set(k for k, v in draft_ab.items() if v == "RESET")

    live_ng = (set(current_ng) | draft_ng) - draft_reset
    live_ok = (set(current_ok) | draft_ok) - draft_reset
    
    all_about_kws = list(about_counts_map.keys())
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

    # 超高速インメモリ転置インデックスによるリアルタイム除外＆残存計算 (0.001〜0.005秒)
    from modules.about_index import get_about_inverted_index, get_cached_title_discarded_records
    about_idx = get_about_inverted_index(duckdb_path, input_path, exclude_ng_types)

    # 1. Step 2-C タイトルNGルールの除外レコードID（キャッシュ参照で 0.000秒）
    ngram_ng_tuple = tuple(sorted(list(ngram_ng_set)))
    title_discarded_ids = get_cached_title_discarded_records(about_idx, ngram_ng_tuple) if link_ngram_rules else set()

    # 2. 確定保存済みルールによる基準件数（ピルクリック時は変化しないため完全キャッシュで 0.000秒）
    @st.cache_data(show_spinner=False)
    def _compute_cached_comm_about_stats(_idx, current_ng_tup, _title_disc_ids, all_kws_tup, tot_cnt):
        comm_ng_set = set(current_ng_tup)
        comm_match = set()
        for kw in all_kws_tup:
            if kw in comm_ng_set:
                comm_match.add(kw)
            else:
                for ng_w in comm_ng_set:
                    if len(ng_w) >= 2 and ng_w in kw:
                        comm_match.add(kw)
                        break
        comm_about_disc = _idx.compute_discarded_records(comm_match)
        comm_disc_ids = comm_about_disc | _title_disc_ids
        c_disc_cnt = len(comm_disc_ids)
        c_rem_cnt = max(0, tot_cnt - c_disc_cnt)
        c_act_counts = _idx.compute_active_counts(comm_disc_ids)
        return comm_disc_ids, c_disc_cnt, c_rem_cnt, c_act_counts, comm_match

    current_ng_tuple = tuple(sorted(list(current_ng)))
    all_about_kws_tuple = tuple(all_about_kws)
    (
        comm_discarded_rec_ids, 
        comm_discarded_cnt, 
        comm_remaining_cnt, 
        comm_active_counts, 
        comm_matched_ng
    ) = _compute_cached_comm_about_stats(
        about_idx, 
        current_ng_tuple, 
        title_discarded_ids, 
        all_about_kws_tuple, 
        total_records_cnt
    )

    # 3. リアルタイム除外＆残存計算（仮設定ドラフトの差分のみ約0.003秒で瞬時算出）
    draft_ng_kws = set(k for k, v in draft_ab.items() if v == "NG")
    draft_reset_kws = set(k for k, v in draft_ab.items() if v == "RESET")

    if not draft_ng_kws and not draft_reset_kws:
        # ドラフトがない場合は基準件数をそのまま使用 (0.000秒)
        discarded_rec_ids = comm_discarded_rec_ids
        discarded_records_cnt = comm_discarded_cnt
        remaining_records_cnt = comm_remaining_cnt
        active_about_counts = comm_active_counts
        about_discarded_ids = comm_discarded_rec_ids - title_discarded_ids
    else:
        # ドラフト差分のみを即時合算 (約0.003秒)
        about_discarded_ids = about_idx.compute_discarded_records(matched_ng_kws)
        discarded_rec_ids = about_discarded_ids | title_discarded_ids
        discarded_records_cnt = len(discarded_rec_ids)
        remaining_records_cnt = max(0, total_records_cnt - discarded_records_cnt)
        active_about_counts = about_idx.compute_active_counts(discarded_rec_ids)

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
        st.markdown("### コントロール ＆ 進捗")
        
        # 0. 個別ピルのクリック判定モード
        st.markdown("##### 個別ピルのクリック判定モード")
        if "click_action_about_mode" not in st.session_state:
            st.session_state["click_action_about_mode"] = "NGに設定"

        click_mode_options = [
            "❌ [除外] NGに設定",
            "✅ [保持] OKに設定",
            "❔ [未判定] に戻す",
            "🔄 トグル切替"
        ]
        mode_map = {
            "❌ [除外] NGに設定": "NGに設定",
            "✅ [保持] OKに設定": "OKに設定",
            "❔ [未判定] に戻す": "未判定に戻す",
            "❓ [未判定] に戻す": "未判定に戻す",
            "🔄 トグル切替": "トグル切替",
            "[除外] NGに設定": "NGに設定",
            "[保持] OKに設定": "OKに設定",
            "[未判定] に戻す": "未判定に戻す",
            "トグル切替": "トグル切替"
        }
        rev_mode_map = {v: k for k, v in mode_map.items()}

        cur_mode_val = st.session_state.get("click_action_about_mode", "NGに設定")
        cur_mode_disp = rev_mode_map.get(cur_mode_val, "❌ [除外] NGに設定")

        chosen_disp = st.radio(
            "ピルクリック時の動作:",
            options=click_mode_options,
            index=click_mode_options.index(cur_mode_disp) if cur_mode_disp in click_mode_options else 0,
            key="rb_global_click_mode",
            help="クラスタ内および単体ボードの各ピルをクリックした際の判定動作を設定します。"
        )
        st.session_state["click_action_about_mode"] = mode_map[chosen_disp]
        st.caption("キーボード: **Q** = ❌ NG除外 ｜ **W** = ✅ OK保持 ｜ **E** = ❔ リセット")

        st.write("---")

        # 1. 絞り込み進捗メトリクス
        st.markdown("##### 絞り込み進捗 (レコード件数)")
        st.metric("初期メタデータセット", f"{total_records_cnt:,} 件")
        if link_ngram_rules and len(title_discarded_ids) > 0:
            st.metric(
                "合算除外 (主題 ＋ タイトル)", 
                f"{discarded_records_cnt:,} 件", 
                delta=f"-{reduction_rate:.1%}", 
                delta_color="inverse",
                help=f"主題除外: {len(about_discarded_ids):,} 件 ＋ タイトル除外: {len(title_discarded_ids):,} 件 (重複排除後: {discarded_records_cnt:,} 件)"
            )
        else:
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
        st.markdown("##### ルール確定 ＆ 保存")
        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]
        draft_count = len(draft_ab)

        def _clear_all_about_order_caches():
            st.session_state.pop("cluster_order_ids", None)
            st.session_state.pop("about_single_order", None)
            for k in list(st.session_state.keys()):
                if k.startswith("cl_kw_order_"):
                    st.session_state.pop(k, None)
            # Step 2-C (N-gram) 側の順序キャッシュも一括消去して完全同期
            for n in range(2, 10):
                st.session_state.pop(f"ngram_order_n_{n}", None)

        def _apply_and_save_about_draft():
            if draft_ab:
                for kw, status in list(draft_ab.items()):
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

                _clear_all_about_order_caches()
                st.session_state["chk_view_ver"] += 1
                st.success("判別結果を確定し about_rules.json へ保存しました。")
                st.rerun()

        if draft_count > 0:
            st.warning(f"現在 **{draft_count} 件** のキーワードが仮選択中です。")
            c_dr1, c_dr2 = st.columns([3, 1.2])
            with c_dr1:
                if st.button(f"仮設定 ({draft_count} 件) を確定保存 ＆ 再ソート", type="primary", use_container_width=True, key="btn_apply_cluster_draft_ctrl"):
                    _apply_and_save_about_draft()
            with c_dr2:
                if st.button("全破棄", type="secondary", use_container_width=True, key="btn_discard_all_about_draft", help="すべての仮選択を取り消します。"):
                    draft_ab.clear()
                    _clear_all_about_order_caches()
                    st.rerun()
        else:
            st.caption("すべてのルールが保存済みです。クラスタやピルを選択すると確定ボタンが表示されます。")

        st.write("---")

        # 3. フィルタ適用実行
        st.markdown("##### フィルタ適用実行")
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
            with st.spinner("About フィルタを適用中..."):
                prog_bar = st.progress(0, text="About フィルタを適用中...")
                tot_for_prog = max(1, total_records_cnt)
                def _prog(cur):
                    prog_bar.progress(min(1.0, cur / tot_for_prog), text=f"処理中: {cur:,} / {tot_for_prog:,} 件")
                passed, disc = run_about_filter(
                    input_path, about_rules_path, about_filtered_path, 
                    f"{data_dir}/discarded_about.csv",
                    progress_callback=_prog
                )
                prog_bar.empty()
            
            st.session_state["cluster_visible_limit"] = int(st.session_state.get("num_clusters_per_page", 10))
            st.session_state["chk_view_ver"] += 1
            st.success(f"About フィルタ完了: 通過 {passed:,} 件 / 除外 {disc:,} 件")
            st.rerun()

        st.write("---")

        # 4. 表示・操作オプション
        st.markdown("##### 表示・操作設定")
        
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
        if st.session_state.get("last_sort_cluster_by") != sort_cluster_by:
            st.session_state["last_sort_cluster_by"] = sort_cluster_by
            st.session_state.pop("cluster_order_ids", None)
        clusters_per_page = st.number_input("1回のクラスタ追加数", min_value=5, max_value=100, value=10, step=5, key="num_clusters_per_page")

        st.write("---")

        # 5. 初期化
        with st.popover("ルール全初期化", help="Aboutルールを初期化"):
            st.warning("About ルール設定 (about_rules.json) を全初期化しますか？")
            st.caption("登録済みの NG / OK パターンがすべて消去されます。")
            if st.button("確定して初期化を実行", type="primary", use_container_width=True, key="btn_confirm_reset_about"):
                st.session_state["edited_noise"] = set()
                st.session_state["edited_strong"] = set()
                st.session_state["draft_about_changes"] = {}
                st.session_state.pop("cluster_order_ids", None)
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
            "クラスタ一括判別 (推奨)",
            "単体キーワード判別ボード",
            "自由入力一括指定 (カスタム)",
            "LLMノイズ候補提案",
            f"登録済ルール管理 ({len(current_ng)} NG / {len(current_ok)} OK)"
        ])

        # ---------------------------------------------------------------------
        # TAB 1: クラスタ一括判別 (推奨)
        # ---------------------------------------------------------------------
        with tab_cluster:
            st.markdown("類似性に基づいて抽出されたキーワード群に対し、一括/個別の判定（OK/NG/未判定）を行います。")

            # オンデマンドキーワード詳細モーダル (クリック時のみDuckDBから該当1件を0.005秒で取得)
            if hasattr(st, "dialog"):
                @st.dialog("主題キーワード詳細・該当資料プレビュー", width="large")
                def _show_about_keyword_dialog(target_kw: str, eff_cnt: int, tot_cnt: int):
                    from components.ndc_utils import format_about_keyword_display
                    from components.file_utils import make_rich_search_links_md, make_jps_item_url
                    disp_target = format_about_keyword_display(target_kw)
                    st.markdown(f"### 『{disp_target}』")
                    st.markdown(make_rich_search_links_md(target_kw))
                    st.markdown(f"- **該当資料件数**: 未除外残存: **{eff_cnt:,} 件** （データセット全体: {tot_cnt:,} 件）")
                    st.write("---")

                    samples = []
                    if use_duckdb:
                        try:
                            db_pop = get_duckdb_manager(duckdb_path) if get_duckdb_manager else DuckDBManager(db_path=duckdb_path)
                            samples = db_pop.get_records_by_about_keyword(target_kw, limit=30, exclude_ng_types=exclude_ng_types)
                        except Exception:
                            samples = []

                    if samples:
                        st.caption(f"代表資料一覧 (上位 {len(samples)} 件 / 全 {tot_cnt:,} 件):")
                        sample_lines = []
                        for rec in samples:
                            r_title = rec.get('title', '') or "（無題）"
                            r_id = rec.get('id', '')
                            creator_part = f" （著者: `{rec.get('creator')}`）" if rec.get('creator') else ""
                            item_link = make_jps_item_url(r_id, r_title)
                            sample_lines.append(f"• [**{r_title}**]({item_link}){creator_part}")
                        if tot_cnt > len(samples):
                            sample_lines.append(f"\n*※ 他 {tot_cnt - len(samples):,} 件の資料があります*")
                        with st.container(height=320):
                            st.markdown("\n".join(sample_lines), unsafe_allow_html=True)
                    else:
                        st.info("現在表示可能な資料がありません。")

            def render_single_cluster_card(c, cid, kws):
                ng_c = sum(1 for k in kws if get_eff_status(k) == "NG")
                ok_c = sum(1 for k in kws if get_eff_status(k) == "OK")
                un_c = len(kws) - ng_c - ok_c

                if ng_c > 0 and ok_c == 0 and un_c == 0:
                    status_badge = "❌ 全除外 (NG)"
                elif ok_c > 0 and ng_c == 0 and un_c == 0:
                    status_badge = "✅ 全保持 (OK)"
                elif ok_c > 0 or ng_c > 0:
                    status_badge = f"混合 (✅{ok_c} / ❌{ng_c} / ❔{un_c})"
                else:
                    status_badge = f"❔ 未判定 (全{un_c}件)"

                from components.ndc_utils import format_about_keyword_display

                # クラスタに属するキーワード件数をO(1)で高速算出
                cl_total_cnt = sum(about_counts_map.get(k, 0) for k in kws)
                cl_comm_cnt = sum(comm_active_counts.get(k, 0) for k in kws) if comm_active_counts is not None else sum(about_counts_map.get(k, 0) for k in kws if k not in comm_matched_ng)
                cl_act_cnt = sum(active_about_counts.get(k, 0) for k in kws) if active_about_counts is not None else sum(about_counts_map.get(k, 0) for k in kws if k not in matched_ng_kws)

                # ピルの絞り込み（判定済み非表示 ＆ 残存0件非表示オプション）
                # [NOTE] 確定保存済みのピルのみ非表示にし、現在選択中の「仮設定ピル (kw in draft_ab)」は保存/確定まで表示を継続！
                visible_kws_info = []
                for kw in kws:
                    tot_kw_cnt = about_counts_map.get(kw, 0)
                    is_in_draft = (kw in draft_ab)
                    if is_in_draft:
                        # 仮設定中のキーワードは、自己除外前の本来の未判定残存件数を保持（最下位ワープを防止）
                        eff_kw_cnt = comm_active_counts.get(kw, 0) if comm_active_counts is not None else tot_kw_cnt
                    elif kw in matched_ng_kws:
                        eff_kw_cnt = 0
                    else:
                        eff_kw_cnt = active_about_counts.get(kw, 0) if active_about_counts is not None else tot_kw_cnt

                    st_val = get_eff_status(kw)
                    is_classified = (st_val in ("OK", "NG")) and not is_in_draft
                    is_zero_remaining = (eff_kw_cnt == 0) and not is_in_draft

                    if hide_fully_classified and is_classified:
                        continue
                    if hide_zero_cluster_pills and is_zero_remaining:
                        continue
                    visible_kws_info.append((kw, eff_kw_cnt, st_val, tot_kw_cnt, is_in_draft))

                # 確定保存されるまではクラスタ内ピルの表示順序を固定（クリック時のワープ・消失を根絶）
                cl_kw_order_key = f"cl_kw_order_{cid}"
                if cl_kw_order_key not in st.session_state:
                    # 初回整列：残存影響度の大きい順に整列
                    visible_kws_info.sort(key=lambda item: (item[1], item[3]), reverse=True)
                    st.session_state[cl_kw_order_key] = [item[0] for item in visible_kws_info]
                else:
                    saved_kws = st.session_state[cl_kw_order_key]
                    info_lookup = {item[0]: item for item in visible_kws_info}
                    # 保存順序に従って配置し、新出キーワードがあれば末尾に追加
                    ordered_info = [info_lookup[k] for k in saved_kws if k in info_lookup]
                    for item in visible_kws_info:
                        if item[0] not in saved_kws:
                            ordered_info.append(item)
                    visible_kws_info = ordered_info

                # 表示すべきピルがなく、かつ仮設定もない場合はクラスタごと非表示
                has_draft = any(k in draft_ab for k in kws)
                if len(visible_kws_info) == 0 and not has_draft:
                    return

                kw_preview = ", ".join([format_about_keyword_display(k, 18) for k in kws[:4]]) + ("..." if len(kws) > 4 else "")
                if has_draft and cl_act_cnt != cl_comm_cnt:
                    cnt_str = f"残存: {cl_comm_cnt:,} 件 ➔ 仮選択後: {cl_act_cnt:,} 件 / 総 {cl_total_cnt:,} 件"
                else:
                    cnt_str = f"残存: {cl_comm_cnt:,} 件 / 総 {cl_total_cnt:,} 件"
                draft_indicator = " ⚡[仮設定中]" if has_draft else ""
                expander_title = f"{c['name']} [{status_badge}]{draft_indicator} （対象語句: {kw_preview} [{len(kws)}種類] ｜ {cnt_str}）"

                with st.expander(expander_title, expanded=True):
                    # 一括操作の対象キーワード選定（既存のOK/NG判定を保護）
                    unclassified_kws = [k for k in kws if get_eff_status(k) == "UN"]
                    is_partial = len(unclassified_kws) < len(kws)
                    target_batch_kws = unclassified_kws if (is_partial or hide_fully_classified) else kws

                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        btn_ok_label = f"✅ 未判定のみ一括 OK [{len(target_batch_kws)}件]" if is_partial else f"✅ 一括 OK 仮設定 [{len(kws)}件]"
                        if st.button(btn_ok_label, key=f"btn_cl_ok_{cid}", type="secondary", use_container_width=True, disabled=(len(target_batch_kws) == 0)):
                            for k in target_batch_kws:
                                draft_ab[k] = "OK"
                            st.rerun()
                    with b_col2:
                        btn_ng_label = f"❌ 未判定のみ一括 NG [{len(target_batch_kws)}件]" if is_partial else f"❌ 一括 NG 仮設定 [{len(kws)}件]"
                        if st.button(btn_ng_label, key=f"btn_cl_ng_{cid}", type="secondary", use_container_width=True, disabled=(len(target_batch_kws) == 0)):
                            for k in target_batch_kws:
                                draft_ab[k] = "NG"
                            st.rerun()
                    with b_col3:
                        if st.button(f"❔ 一括 未判定リセット", key=f"btn_cl_reset_{cid}", use_container_width=True):
                            for k in kws:
                                if k in current_ng or k in current_ok:
                                    draft_ab[k] = "RESET"
                                else:
                                    draft_ab.pop(k, None)
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
                            
                            if eff_kw_cnt == 0:
                                cnt_badge = f" [残存0件/全{tot_kw_cnt:,}件]"
                            elif eff_kw_cnt != tot_kw_cnt:
                                cnt_badge = f" ({eff_kw_cnt:,}件/全{tot_kw_cnt:,}件)"
                            else:
                                cnt_badge = f" ({tot_kw_cnt:,}件)"

                            draft_tag = " [仮]" if is_in_draft else ""
                            if st_val == "OK":
                                lbl = f"✅ {disp_k}{cnt_badge}{draft_tag}"
                            elif st_val == "NG":
                                lbl = f"❌ {disp_k}{cnt_badge}{draft_tag}"
                            else:
                                lbl = f"❔ {disp_k}{cnt_badge}{draft_tag}"

                            c_btn_k, c_pop_k = col_k.columns([5.1, 0.9])
                            with c_btn_k:
                                if st.button(lbl, key=f"tgl_kw_{cid}_{kw}", use_container_width=True):
                                    cur_m = st.session_state.get("click_action_about_mode", "NGに設定")
                                    if cur_m == "NGに設定":
                                        if kw in draft_ab and draft_ab[kw] == "NG":
                                            draft_ab.pop(kw, None)
                                        else:
                                            draft_ab[kw] = "NG"
                                    elif cur_m == "OKに設定":
                                        if kw in draft_ab and draft_ab[kw] == "OK":
                                            draft_ab.pop(kw, None)
                                        else:
                                            draft_ab[kw] = "OK"
                                    elif cur_m == "未判定に戻す":
                                        if kw in current_ng or kw in current_ok:
                                            draft_ab[kw] = "RESET"
                                        else:
                                            draft_ab.pop(kw, None)
                                    else:
                                        if st_val == "OK":
                                            draft_ab[kw] = "NG"
                                        elif st_val == "NG":
                                            if kw in current_ng or kw in current_ok:
                                                draft_ab[kw] = "RESET"
                                            else:
                                                draft_ab.pop(kw, None)
                                        else:
                                            draft_ab[kw] = "OK"
                                    st.rerun()
                            with c_pop_k:
                                if st.button("⋮", key=f"btn_det_{cid}_{kw}", use_container_width=True):
                                    if hasattr(st, "dialog"):
                                        _show_about_keyword_dialog(kw, eff_kw_cnt, tot_kw_cnt)
                                    else:
                                        st.session_state["selected_about_detail_kw"] = (kw, eff_kw_cnt, tot_kw_cnt)
                                        st.rerun()

                        if len(visible_kws_info) > cur_kw_limit:
                            rem_kw_cnt = len(visible_kws_info) - cur_kw_limit
                            if st.button(f"クラスタ内の残りのキーワード ({rem_kw_cnt}件) をすべて表示", key=f"btn_more_kws_{cid}", use_container_width=True):
                                st.session_state[cl_limit_key] = len(visible_kws_info)
                                st.rerun()

            # 各キーワードのアクティブ残存件数は辞書参照でO(1)
            def _get_eff_k_cnt(k):
                if k in matched_ng_kws:
                    return 0
                return active_about_counts.get(k, 0) if active_about_counts is not None else about_counts_map.get(k, 0)

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
                        
                        eff_k_cnt = _get_eff_k_cnt(k)
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

                    # クラスタの残存件数をO(1)で計算
                    cl_tot_cnt = sum(about_counts_map.get(k, 0) for k in kws)
                    cl_comm_cnt = sum(comm_active_counts.get(k, 0) for k in kws) if comm_active_counts is not None else sum(about_counts_map.get(k, 0) for k in kws if k not in comm_matched_ng)
                    cl_act_cnt = sum(active_about_counts.get(k, 0) for k in kws) if active_about_counts is not None else sum(about_counts_map.get(k, 0) for k in kws if k not in matched_ng_kws)

                    if hide_zero_cluster_pills and cl_act_cnt == 0 and not has_draft_in_cluster:
                        continue

                    display_clusters.append({
                        **c,
                        "ng_count": ng_c,
                        "ok_count": ok_c,
                        "un_count": un_c,
                        "active_count": cl_comm_cnt,
                        "realtime_active_count": cl_act_cnt,
                        "unique_total_count": cl_tot_cnt,
                        "visible_kws_count": len(cluster_visible_kws),
                        "has_draft": has_draft_in_cluster
                    })

                # 確定保存＆再ソートが実行されるまでは現在の表示順を完全に固定
                if "cluster_order_ids" not in st.session_state:
                    if sort_cluster_by == "所属キーワード数順":
                        display_clusters.sort(key=lambda x: len(x["keywords"]), reverse=True)
                    else:
                        display_clusters.sort(key=lambda x: x["active_count"], reverse=True)
                    st.session_state["cluster_order_ids"] = [c["cluster_id"] for c in display_clusters]
                else:
                    order_map = {cid: idx for idx, cid in enumerate(st.session_state["cluster_order_ids"])}
                    display_clusters.sort(key=lambda x: order_map.get(x["cluster_id"], 999999))

                total_display_clusters = len(display_clusters)

                if total_display_clusters == 0:
                    st.success("表示条件に一致する未判定のクラスタはありません。")
                    return

                if "cluster_visible_limit" not in st.session_state:
                    st.session_state["cluster_visible_limit"] = int(clusters_per_page)

                cur_cl_limit = min(total_display_clusters, max(int(clusters_per_page), int(st.session_state.get("cluster_visible_limit", clusters_per_page))))
                st.session_state["cluster_visible_limit"] = cur_cl_limit

                st.markdown(f"<div class='facet-hint'>全 {total_display_clusters} クラスタ中 {cur_cl_limit} クラスタを表示中</div>", unsafe_allow_html=True)

                page_clusters = display_clusters[:cur_cl_limit]

                # ページ内表示キーワードを一括事前解決 (描画ループ内での多重呼び出しを防止)
                from components.ndc_utils import prefetch_about_keywords_batch
                page_all_kws = [k for c in page_clusters for k in c["keywords"][:24]]
                if page_all_kws:
                    prefetch_about_keywords_batch(page_all_kws, max_items=len(page_all_kws))

                st.write("---")

                for c in page_clusters:
                    render_single_cluster_card(c, c["cluster_id"], c["keywords"])

                # ボトムの追加読み込み
                if cur_cl_limit < total_display_clusters:
                    st.write("---")
                    btn_cl_txt = f"次の {int(clusters_per_page)} クラスタを読み込む (現在 {cur_cl_limit} / 全 {total_display_clusters} クラスタ)"
                    if st.button(btn_cl_txt, key="btn_bot_more_clusters", type="secondary", use_container_width=True):
                        st.session_state["cluster_visible_limit"] = min(total_display_clusters, cur_cl_limit + int(clusters_per_page))
                        st.rerun()
                else:
                    st.caption(f"全 {total_display_clusters} クラスタを表示完了しました。")

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
            c_ab_s1, c_ab_s2 = st.columns([3, 2])
            with c_ab_s1:
                sort_about_mode = st.radio(
                    "並び順:",
                    options=["未判定影響度順", "全体出現頻度順"],
                    horizontal=True,
                    key="sort_about_mode",
                    help="未判定影響度順: 現在の未除外データの中で多くヒットする（フィルタリング影響の大きい）順に並べます。"
                )
            with c_ab_s2:
                hide_zero_about = st.checkbox(
                    "残存未判定 0 件を非表示", 
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

        b1 = c_m1.button("【 Q 】 ❌ NG除外モード", key="btn_shortcut_ab_q", type=btn1_type, use_container_width=True)
        b2 = c_m2.button("【 W 】 ✅ OK保持モード", key="btn_shortcut_ab_w", type=btn2_type, use_container_width=True)
        b3 = c_m3.button("【 E 】 ❔ 未判定リセット", key="btn_shortcut_ab_e", type=btn3_type, use_container_width=True)

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
            st.error("【現在の設定モード: ❌ NG (除外)】 (ショートカット: Q)")
        elif click_action_mode == "OKに設定":
            st.success("【現在の設定モード: ✅ OK (保持)】 (ショートカット: W)")
        elif click_action_mode == "未判定に戻す":
            st.info("【現在の設定モード: ❔ 未判定リセット】 (ショートカット: E)")

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
        # 残存未判定件数 (eff_cnt) の算出 (辞書参照でO(1))
        kw_eff_counts = {}
        for kw, cnt in filtered_ranking:
            if kw in draft_ab:
                # 仮設定中のキーワードは、自己除外前の本来の未判定残存件数を保持（最下位ワープを防止）
                eff_c = comm_active_counts.get(kw, 0) if comm_active_counts is not None else cnt
            elif kw in matched_ng_kws:
                eff_c = 0
            else:
                eff_c = active_about_counts.get(kw, 0) if active_about_counts is not None else cnt
            kw_eff_counts[kw] = eff_c

        # 確定保存＆再ソートが押されるまでは、表示順序とピル集合を完全に固定
        single_order_key = "about_single_order"
        last_about_sort_key = "last_about_sort_mode"
        last_about_hide_zero_key = "last_about_hide_zero"
        if (st.session_state.get(last_about_sort_key) != sort_about_mode or
            st.session_state.get(last_about_hide_zero_key) != hide_zero_about):
            st.session_state.pop(single_order_key, None)
            st.session_state[last_about_sort_key] = sort_about_mode
            st.session_state[last_about_hide_zero_key] = hide_zero_about

        if single_order_key not in st.session_state:
            initial_ranking = list(filtered_ranking)
            if hide_zero_about:
                initial_ranking = [
                    (kw, cnt) for kw, cnt in initial_ranking 
                    if kw_eff_counts.get(kw, 0) > 0 or kw in current_ng or kw in current_ok or kw in draft_ab
                ]
            if sort_about_mode == "未判定影響度順":
                initial_ranking.sort(
                    key=lambda item: (kw_eff_counts.get(item[0], 0), item[1]),
                    reverse=True
                )
            else:
                initial_ranking.sort(key=lambda item: item[1], reverse=True)
            st.session_state[single_order_key] = [it[0] for it in initial_ranking]

        # 保存された順序リストから表示アイテムを復元（ドラフト編集中はピルが消えたり動いたりしない）
        saved_single_kws = st.session_state[single_order_key]
        rank_lookup = {item[0]: item for item in filtered_ranking}
        display_ranking = []
        for k in saved_single_kws:
            if k not in rank_lookup:
                continue
            eff_c = kw_eff_counts.get(k, 0)
            # 他条件（タイトル除外や他NGルール）で残存0件になった未判定キーワードは確実に非表示！
            # ただし、操作中の仮設定ピル（k in draft_ab）や確定済みピルは表示を維持
            if hide_zero_about and eff_c == 0 and k not in draft_ab and k not in current_ng and k not in current_ok:
                continue
            display_ranking.append(rank_lookup[k])

        class LazySamplesMap(dict):
            def __init__(self, db_p, counts_map, kw_eff, use_db, exclude_types):
                self.db_p = db_p
                self.counts_map = counts_map
                self.kw_eff = kw_eff
                self.use_db = use_db
                self.exclude_types = exclude_types

            def get(self, kw, default=None):
                eff_c = self.kw_eff.get(kw, 0)
                samples_list = []
                if self.use_db and os.path.exists(self.db_p) and DuckDBManager is not None:
                    try:
                        db = get_duckdb_manager(self.db_p) if get_duckdb_manager else DuckDBManager(db_path=self.db_p)
                        samples_list = db.get_records_by_about_keyword(kw, limit=10, exclude_ng_types=self.exclude_types)
                    except Exception:
                        samples_list = []
                return {
                    "eff_cnt": eff_c,
                    "samples": samples_list
                }
        
        active_samples_info = LazySamplesMap(duckdb_path, about_counts_map, kw_eff_counts, use_duckdb, exclude_ng_types)

        if "draft_about_changes" not in st.session_state:
            st.session_state["draft_about_changes"] = {}
        draft_ab = st.session_state["draft_about_changes"]

        # 汎用ピルボードコンポーネント呼出
        render_pill_board(
            items=display_ranking,
            active_samples_map=active_samples_info,
            current_ng=current_ng,
            current_ok=current_ok,
            draft_dict=draft_ab,
            click_action_mode=click_action_mode,
            page_session_key="about_single_page",
            on_confirm_save=_apply_and_save_about_draft
        )

        c_hdr1, c_hdr2 = st.columns([3, 2])
        with c_hdr1:
            st.markdown(f"判定対象キーワード (該当: **{len(display_ranking)}** 件)")
        with c_hdr2:
            draft_count = len(draft_ab)
            if draft_count > 0:
                if st.button(f"仮設定 ({draft_count} 件) を確定して保存", type="primary", use_container_width=True, key="btn_single_draft_apply"):
                    _apply_and_save_about_draft()
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
            st.markdown(f"#### 入力された {len(parsed_custom_ab)} 件のキーワードのヒット検証")
            
            ab_hit_stats = []
            total_impact_docs = set()
            active_impact_docs = set()

            for kw in parsed_custom_ab:
                doc_indices = list(about_idx.kw_to_rec_ids.get(kw, set()))
                act_indices = [idx for idx in doc_indices if idx not in discarded_rec_ids]
                
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
                if st.button(f"指定した {len(parsed_custom_ab)} 語を一括で NG (除外) ルールへ追加", type="primary", use_container_width=True, key="btn_apply_about_custom_ng"):
                    for kw in parsed_custom_ab:
                        current_ng.add(kw)
                        current_ok.discard(kw)
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)
                    _clear_all_about_order_caches()
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_ab)} 件のキーワードを NG ルールへ登録しました。")
                    st.rerun()

            with c_a2:
                if st.button(f"指定した {len(parsed_custom_ab)} 語を一括で OK (保持) ルールへ追加", type="secondary", use_container_width=True, key="btn_apply_about_custom_ok"):
                    for kw in parsed_custom_ab:
                        current_ok.add(kw)
                        current_ng.discard(kw)
                    save_dict = {}
                    for k in current_ng: save_dict[k] = "NG"
                    for k in current_ok: save_dict[k] = "OK"
                    safe_save_json(save_dict, about_rules_path)
                    _clear_all_about_order_caches()
                    st.session_state["chk_view_ver"] += 1
                    st.cache_data.clear()
                    st.success(f"{len(parsed_custom_ab)} 件のキーワードを OK ルールへ登録しました。")
                    st.rerun()

            with c_a3:
                if st.button("入力クリア", use_container_width=True, key="btn_clear_about_custom_input"):
                    st.session_state["about_custom_txt_ver"] += 1
                    st.rerun()

            st.write("---")
            st.markdown("##### キーワード別ヒット詳細 ＆ 該当資料例")
            for stat in ab_hit_stats:
                kw = stat["keyword"]
                tot_h = stat["total_hits"]
                act_h = stat["active_hits"]
                cur_st = stat["status"]
                
                if cur_st == "NG":
                    st_badge = "❌ [NG登録済]"
                elif cur_st == "OK":
                    st_badge = "✅ [OK登録済]"
                else:
                    st_badge = "❔ [未登録]"

                exp_header = f"『{kw}』 [全 {tot_h:,} 件ヒット / 未判定: {act_h:,} 件] ｜ {st_badge}"
                with st.expander(exp_header, expanded=(tot_h > 0 and cur_st == "未登録")):
                    c_k1, c_k2 = st.columns([3, 1])
                    with c_k1:
                        st.markdown(make_rich_search_links_md(kw))
                    with c_k2:
                        if cur_st != "NG":
                            if st.button(f"『{kw}』をNGに登録", key=f"btn_cust_ab_ng_{kw}", use_container_width=True):
                                current_ng.add(kw)
                                current_ok.discard(kw)
                                save_dict = {}
                                for k in current_ng: save_dict[k] = "NG"
                                for k in current_ok: save_dict[k] = "OK"
                                safe_save_json(save_dict, about_rules_path)
                                _clear_all_about_order_caches()
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            if st.button(f"『{kw}』のNG解除", key=f"btn_cust_ab_del_{kw}", use_container_width=True):
                                current_ng.discard(kw)
                                save_dict = {}
                                for k in current_ng: save_dict[k] = "NG"
                                for k in current_ok: save_dict[k] = "OK"
                                safe_save_json(save_dict, about_rules_path)
                                _clear_all_about_order_caches()
                                st.session_state["chk_view_ver"] += 1
                                st.cache_data.clear()
                                st.rerun()

                    st.caption(f"該当する資料の具体例 (先頭 {len(stat['doc_indices'])} 件):")
                    from components.file_utils import make_jps_keyword_url
                    for idx_doc in stat["doc_indices"]:
                        r_title = about_idx.rec_id_to_title.get(idx_doc, f"レコード #{idx_doc}")
                        jps_url = make_jps_keyword_url(r_title)
                        st.markdown(f"• [**{r_title}**]({jps_url})")
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
                st.warning(f"LLMが抽出したノイズ候補 (全 {len(suggs)} 件)")
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
                st.markdown(f"##### 登録済 NG (除外) ルール [{len(current_ng)} 件]")
                if current_ng:
                    ng_sorted = sorted(list(current_ng))
                    for kw in ng_sorted:
                        disp_k = format_about_keyword_display(kw)
                        c_w, c_del = st.columns([5, 1])
                        with c_w:
                            st.markdown(f"• **{disp_k}**")
                        with c_del:
                            if st.button("削除", key=f"del_mng_ng_{kw}", use_container_width=True):
                                current_ng.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.rerun()
                else:
                    st.info("登録済みの NG ルールはありません。")

            with c_mng2:
                st.markdown(f"##### 登録済 OK (保持) ルール [{len(current_ok)} 件]")
                if current_ok:
                    ok_sorted = sorted(list(current_ok))
                    for kw in ok_sorted:
                        disp_k = format_about_keyword_display(kw)
                        c_w, c_del = st.columns([5, 1])
                        with c_w:
                            st.markdown(f"• **{disp_k}**")
                        with c_del:
                            if st.button("削除", key=f"del_mng_ok_{kw}", use_container_width=True):
                                current_ok.discard(kw)
                                save_dict = {k: "NG" for k in current_ng}
                                save_dict.update({k: "OK" for k in current_ok})
                                safe_save_json(save_dict, about_rules_path)
                                st.session_state["chk_view_ver"] += 1
                                st.rerun()
                else:
                    st.info("登録済みの OK ルールはありません。")

    # 最下部ナビゲーション
    render_step_navigation(
        prev_choice="Step 2-A: データ種別 (rdf:type) 分析・除外",
        next_choice="Step 2-C: タイトル語彙・文字列パターン分析・除外"
    )



