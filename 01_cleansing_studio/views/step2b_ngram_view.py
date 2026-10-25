# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 2-B: タイトル N-Gram (N=2〜9) パターン分析・除外ビュー
"""
import json
import math
import os
import re
import urllib.parse
from collections import Counter, defaultdict
import streamlit as st

from components.file_utils import safe_save_json, make_rich_search_links_md
from components.pill_board import render_pill_board
from modules.ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter, clean_title_text

try:
    import streamlit_hotkeys as hotkeys
except Exception:
    hotkeys = None


def render_step2b_view(paths: dict):
    """Step 2-C 画面の描画"""
    st.title("Step 2-C: タイトル語彙・文字列パターン（N-Gram / 任意キーワード）分析・除外")
    st.markdown("資料タイトルに含まれる頻出語彙（N=2〜9のN-Gram部分文字列）の集計・抽出に加え、任意の文字列・キーワードを指定した除外（🚫 NG）および合格確定（✅ OK: LLMスキップ）ルールの作成を行います。")

    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    raw_metadata_path = paths['PATH_RAW_METADATA']
    ngram_rules_path = paths['PATH_NGRAM_RULES']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    data_dir = os.path.dirname(ngram_filtered_path)

    if not os.path.exists(raw_metadata_path):
        st.warning("対象データが存在しません。先に Step 1 で初期メタデータセットを取得してください。")
        st.stop()

    os.makedirs(os.path.dirname(ngram_rules_path), exist_ok=True)

    # --- 📁 入力データソースの選択 ＆ 前段相互連携コントロール ---
    data_source_options = []
    if os.path.exists(about_filtered_path):
        data_source_options.append("Step 2-B (主題 about) 適用後データ (about_filtered.jsonl)")
    if os.path.exists(type_filtered_path):
        data_source_options.append("Step 2-A (データ種別) 適用後データ (type_filtered.jsonl)")
    data_source_options.append("初期メタデータセット全件 (raw_metadata.jsonl)")

    c_src1, c_src2 = st.columns([3, 2])
    with c_src1:
        chosen_source = st.selectbox(
            "📁 分析対象データソース:",
            options=data_source_options,
            index=0,
            help="前段で除外されたデータ種別や主題ノイズをあらかじめ省いた状態で Step 2-C の分析を行うことができます。",
            key="sb_step2b_data_source"
        )
    
    if "about_filtered" in chosen_source:
        input_path = about_filtered_path
    elif "type_filtered" in chosen_source:
        input_path = type_filtered_path
    else:
        input_path = raw_metadata_path

    if not os.path.exists(input_path):
        input_path = raw_metadata_path

    with c_src2:
        if "about_filtered" in chosen_source:
            st.success("✅ Step 2-B の除外結果を反映したデータセットで分析中")
        elif "type_filtered" in chosen_source:
            st.success("✅ Step 2-A の除外結果を反映したデータセットで分析中")
        else:
            st.caption("ℹ️ 初期メタデータセット全件を対象に分析中")

    if "edited_ngram_ng" not in st.session_state:
        ngram_rules = {}
        if os.path.exists(ngram_rules_path):
            with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                ngram_rules = json.load(f)
        st.session_state["edited_ngram_ng"] = set([k for k, v in ngram_rules.items() if v == "NG"])
        st.session_state["edited_ngram_ok"] = set([k for k, v in ngram_rules.items() if v == "OK"])

    if "ngram_view_ver" not in st.session_state:
        st.session_state["ngram_view_ver"] = 0

    ngram_ng = st.session_state["edited_ngram_ng"]
    ngram_ok = st.session_state["edited_ngram_ok"]

    @st.cache_data(show_spinner=False)
    def load_filtered_titles(file_path, file_mtime):
        titles_data = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        item = json.loads(line)
                        label_val = item.get("rdfs:label", item.get("schema:name", ""))
                        title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)
                        titles_data.append(title_str)
                    except Exception:
                        continue
        return titles_data

    min_n = 2
    max_n = 9

    input_mtime = os.path.getmtime(input_path) if os.path.exists(input_path) else 0
    input_titles = load_filtered_titles(input_path, input_mtime)

    @st.cache_data(show_spinner=False)
    def get_cached_ngrams_from_titles_fast(file_path, file_mtime, min_n=min_n, max_n=max_n):
        titles = load_filtered_titles(file_path, file_mtime)
        counts = {n: Counter() for n in range(min_n, max_n + 1)}
        samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

        # 大規模データ時のサンプリング (最大5万件で上位ランキングを高速推定)
        scan_titles = titles if len(titles) <= 50000 else titles[:50000]

        for title in scan_titles:
            clean_title = clean_title_text(title)
            for n in range(min_n, max_n + 1):
                if len(clean_title) >= n:
                    ngrams = [clean_title[i:i+n] for i in range(len(clean_title) - n + 1)]
                    for word in set(ngrams):
                        counts[n][word] += 1
                        if len(samples[n][word]) < 30 and title not in samples[n][word]:
                            samples[n][word].append(title)

        result_dict = {}
        for n in range(min_n, max_n + 1):
            ranking = []
            for word, count in counts[n].most_common(500):
                if count >= 2:
                    ranking.append((word, count, samples[n][word]))
            result_dict[n] = ranking
        return result_dict

    ngram_dict = get_cached_ngrams_from_titles_fast(input_path, input_mtime)
    total_input_records = len(input_titles)

    @st.cache_data(show_spinner=False)
    def count_ngram_discarded_records(file_path, file_mtime, ng_rules_tuple):
        if not ng_rules_tuple:
            return 0
        titles = load_filtered_titles(file_path, file_mtime)
        disc_cnt = 0
        for title in titles:
            if any(pattern in title for pattern in ng_rules_tuple):
                disc_cnt += 1
        return disc_cnt

    ngram_discarded_records = count_ngram_discarded_records(input_path, input_mtime, tuple(sorted(list(ngram_ng))))
    ngram_remaining_records = total_input_records - ngram_discarded_records
    ngram_reduction_rate = (ngram_discarded_records / max(1, total_input_records))

    @st.cache_data(show_spinner=False)
    def get_cached_active_titles(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple=None):
        titles = load_filtered_titles(file_path, file_mtime)
        res = []
        for t in titles:
            if not t:
                continue
            if ng_rules_tuple and any(ng in t for ng in ng_rules_tuple):
                continue
            if ok_rules_tuple and any(ok in t for ok in ok_rules_tuple):
                continue
            res.append(t)
        return res

    active_titles = get_cached_active_titles(
        input_path, 
        input_mtime, 
        tuple(sorted(list(ngram_ng))),
        tuple(sorted(list(ngram_ok)))
    )

    def get_parent_rule(word: str, ng_set: set, ok_set: set) -> tuple:
        for ng in sorted(list(ng_set), key=len):
            if len(ng) < len(word) and ng in word:
                return "NG", ng
        for ok in sorted(list(ok_set), key=len):
            if len(ok) < len(word) and ok in word:
                return "OK", ok
        return None, None

    def build_expanded_ngram_rules(ng_set, ok_set, all_ngram_dict):
        expanded = {}
        for ng_w in ng_set:
            expanded[ng_w] = "NG"
        for ok_w in ok_set:
            expanded[ok_w] = "OK"

        for n, ranking in all_ngram_dict.items():
            for word, count, _ in ranking:
                if word in expanded:
                    continue
                p_type, p_word = get_parent_rule(word, ng_set, ok_set)
                if p_type:
                    expanded[word] = p_type
        return expanded

    # 3カラム / 2ペイン レイアウト（左: メイン作業領域 70% ｜ 右: 固定コントロール＆進捗パネル 30%）
    col_main, col_ctrl = st.columns([7, 3])

    # =========================================================================
    # 右側: 固定コントロール ＆ アクションパネル
    # =========================================================================
    with col_ctrl:
        st.markdown("### 🎛️ コントロール ＆ 進捗")

        # 1. 絞り込み進捗メトリクス
        st.markdown("##### 📊 N-Gram 絞り込み進捗")
        st.metric("About通過後レコード", f"{total_input_records:,} 件")
        st.metric(
            "N-Gram 除外対象 (削ぎ落とし)", 
            f"{ngram_discarded_records:,} 件", 
            delta=f"-{ngram_reduction_rate:.1%}", 
            delta_color="inverse"
        )
        st.metric(
            "本工程通過残存レコード", 
            f"{ngram_remaining_records:,} 件", 
            delta=f"{ngram_remaining_records/max(1,total_input_records):.1%}"
        )
        st.metric(
            "登録ルール総数", 
            f"NG: {len(ngram_ng)} 件 / OK: {len(ngram_ok)} 件"
        )

        st.write("---")

        # 2. 仮設定の一括適用 ＆ 保存アクション
        st.markdown("##### ⚡ ルール確定 ＆ 保存")
        
        all_draft_keys = [k for k in st.session_state.keys() if k.startswith("draft_n_")]
        total_draft_cnt = sum(len(st.session_state[k]) for k in all_draft_keys if isinstance(st.session_state[k], dict))

        if total_draft_cnt > 0:
            st.warning(f"現在 **{total_draft_cnt} 件** のパターンが仮選択中です。")
            if st.button(f"⚡ 全仮設定 ({total_draft_cnt} 件) を確定適用", type="primary", use_container_width=True, key="btn_apply_all_ngram_draft_ctrl"):
                for dk in all_draft_keys:
                    d_map = st.session_state[dk]
                    if isinstance(d_map, dict):
                        for w, status in d_map.items():
                            if status == "NG":
                                ngram_ng.add(w)
                                ngram_ok.discard(w)
                            elif status == "OK":
                                ngram_ok.add(w)
                                ngram_ng.discard(w)
                            elif status == "RESET":
                                ngram_ng.discard(w)
                                ngram_ok.discard(w)
                        d_map.clear()
                
                save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                safe_save_json(save_dict, ngram_rules_path)
                st.session_state["ngram_view_ver"] += 1
                st.cache_data.clear()
                st.success("判別結果をルールへ確定適用・保存しました。")
                st.rerun()
        else:
            st.caption("各タブで OK / NG を選択後、ここで一括確定できます。")

        if st.button("💾 ngram_rules.json に手動保存", use_container_width=True, key="btn_save_ngram_rules_ctrl"):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            safe_save_json(save_dict, ngram_rules_path)
            st.success(f"N-Gram ルールを保存しました (全 {len(save_dict):,} ルール)。")

        st.write("---")

        # 3. フィルタ適用実行
        st.markdown("##### 🚀 フィルタ適用実行")
        if st.button("N-Gram フィルタを実行する", type="primary", use_container_width=True, key="btn_run_ngram_filter_ctrl"):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            safe_save_json(save_dict, ngram_rules_path)

            passed, disc = run_ngram_filter(input_path, ngram_rules_path, ngram_filtered_path, f"{data_dir}/discarded_ngram.csv")
            st.cache_data.clear()
            st.success(f"N-Gram フィルタリング完了: 通過 {passed:,} 件 / 除外 {disc:,} 件 (除外ログ: {data_dir}/discarded_ngram.csv)")

        st.write("---")

        # 4. 初期化
        with st.popover("🗑️ ルール全初期化", help="N-Gramルールを初期化"):
            st.warning("N-Gram ルール (`ngram_rules.json`) を全初期化しますか？")
            st.caption("登録済みの全 N-gram NG / OK パターンが消去されます。")
            if st.button("確定して初期化を実行", type="primary", use_container_width=True, key="btn_confirm_reset_ngram_ctrl"):
                st.session_state["edited_ngram_ng"] = set()
                st.session_state["edited_ngram_ok"] = set()
                for key in list(st.session_state.keys()):
                    if key.startswith("draft_n_"):
                        st.session_state[key] = {}
                safe_save_json({}, ngram_rules_path)

                for p_rm in [ngram_filtered_path, f"{data_dir}/discarded_ngram.csv"]:
                    if os.path.exists(p_rm):
                        try:
                            os.remove(p_rm)
                        except Exception:
                            pass
                st.cache_data.clear()
                st.session_state["ngram_view_ver"] += 1
                st.success("N-Gram ルールおよびフィルタ結果を初期化しました。")
                st.rerun()

    # =========================================================================
    # 左側: メイン作業領域 (3タブ構成: キーワード検索＆一括除外 / N-Gram分析 / 管理)
    # =========================================================================
    with col_main:
        tab_search, tab_ngram_board, tab_rules = st.tabs([
            "🎯 タイトルキーワード検索 ＆ 一括除外",
            "🧩 頻出 N-Gram パターン分析 (N=2〜9)",
            f"📋 登録済ルール ({len(ngram_ng)} NG / {len(ngram_ok)} OK)"
        ])

        # ---------------------------------------------------------------------
        # TAB 1: タイトルキーワード検索 ＆ 一括除外 (単語検索・複数一括の両対応)
        # ---------------------------------------------------------------------
        with tab_search:
            st.markdown("### 🎯 タイトルキーワード検索 ＆ 一括除外・保持指定")
            st.caption("除外したい単語を1語で検索して該当資料を確認しながら判定することも、複数の単語（カンマや改行区切り）をまとめて一括登録することも可能です。")

            if "ngram_custom_txt_ver" not in st.session_state:
                st.session_state["ngram_custom_txt_ver"] = 0
            txt_ver_n = st.session_state["ngram_custom_txt_ver"]
            txt_key_n = f"txt_unified_ngram_kws_{txt_ver_n}"

            custom_ngram_input = st.text_area(
                "検索・除外したいキーワード (1語の検索、またはカンマ・改行区切りで複数一括入力):",
                placeholder="例: ピアノ\nまたは\n近代, 洋楽, ピアノ, 教科書, カタログ, 報告書, 地図",
                height=75,
                key=txt_key_n
            )

            parsed_custom_kws = [
                w.strip() for w in re.split(r"[\n,、・/／\s]+", custom_ngram_input) if len(w.strip()) >= 1
            ]
            parsed_custom_kws = list(dict.fromkeys(parsed_custom_kws))

            if len(parsed_custom_kws) == 1:
                # -------------------------------------------------------------
                # 【単一キーワード入力時】: ハイライト付きダイレクト詳細ビュー
                # -------------------------------------------------------------
                kw_q = parsed_custom_kws[0]
                kw_q_lower = kw_q.lower()

                matched_records = []
                for idx, t in enumerate(input_titles):
                    if kw_q_lower in t.lower():
                        is_active = (t in active_titles)
                        matched_records.append({
                            "title": t,
                            "is_active": is_active
                        })

                tot_hit = len(matched_records)
                act_hit = sum(1 for r in matched_records if r["is_active"])

                is_q_ng = kw_q in ngram_ng
                is_q_ok = kw_q in ngram_ok
                if is_q_ng:
                    cur_status_badge = "🚫 [NGルール登録済]"
                elif is_q_ok:
                    cur_status_badge = "✅ [OKルール登録済]"
                else:
                    cur_status_badge = "❓ [未登録]"

                st.markdown(f"#### 📊 『**{kw_q}**』のヒット結果: 全 **{tot_hit:,}** 件 （未除外残存: **{act_hit:,}** 件） ｜ {cur_status_badge}")
                st.markdown(make_rich_search_links_md(kw_q))

                # アクションボタン
                c_act_b1, c_act_b2, c_act_b3 = st.columns([2, 2, 1])
                with c_act_b1:
                    if not is_q_ng:
                        if st.button(f"🚫 『{kw_q}』を NG (除外) ルールに追加", type="primary", use_container_width=True, key=f"btn_add_uni_ng_{kw_q}"):
                            ngram_ng.add(kw_q)
                            ngram_ok.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"『{kw_q}』を NG ルールへ登録しました (ヒット {tot_hit:,} 件が除外対象になります)。")
                            st.rerun()
                    else:
                        if st.button(f"↩️ 『{kw_q}』の NG 登録を解除", use_container_width=True, key=f"btn_rm_uni_ng_{kw_q}"):
                            ngram_ng.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"『{kw_q}』の NG 登録を解除しました。")
                            st.rerun()

                with c_act_b2:
                    if not is_q_ok:
                        if st.button(f"✅ 『{kw_q}』を OK (保持) ルールに追加", type="secondary", use_container_width=True, key=f"btn_add_uni_ok_{kw_q}"):
                            ngram_ok.add(kw_q)
                            ngram_ng.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"『{kw_q}』を OK ルールへ登録しました。")
                            st.rerun()
                    else:
                        if st.button(f"↩️ 『{kw_q}』の OK 登録を解除", use_container_width=True, key=f"btn_rm_uni_ok_{kw_q}"):
                            ngram_ok.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"『{kw_q}』の OK 登録を解除しました。")
                            st.rerun()

                with c_act_b3:
                    if st.button("🔄 クリア", use_container_width=True, key="btn_clear_uni_single"):
                        st.session_state["ngram_custom_txt_ver"] += 1
                        st.rerun()

                st.write("---")
                st.caption(f"📄 **該当タイトル一覧 (全 {tot_hit:,} 件をスクロール確認可能)**:")

                with st.container(height=450):
                    if not matched_records:
                        st.info("条件に一致する資料はありません。")
                    
                    max_disp_d = min(tot_hit, 300)
                    for item in matched_records[:max_disp_d]:
                        raw_t = item["title"]
                        act_tag = "" if item["is_active"] else " <span style='color:#888; font-size:0.75rem;'>[既除外]</span>"
                        
                        from components.file_utils import make_jps_keyword_url
                        hl_t = re.sub(
                            re.escape(kw_q), 
                            f"<mark style='background:#ff4b4b; color:white; padding:1px 4px; border-radius:3px;'>{kw_q}</mark>", 
                            raw_t, 
                            flags=re.IGNORECASE
                        )
                        jps_link = make_jps_keyword_url(raw_t)
                        
                        st.markdown(f"• [📖 **{hl_t}**]({jps_link}){act_tag}", unsafe_allow_html=True)

                    if tot_hit > max_disp_d:
                        st.caption(f"※ パフォーマンス保護のため現在上位 {max_disp_d} 件を表示しています。")

            elif len(parsed_custom_kws) > 1:
                # -------------------------------------------------------------
                # 【複数キーワード入力時】: 合算インパクト＆バッチ一括登録ビュー
                # -------------------------------------------------------------
                st.markdown(f"#### 🔍 入力された {len(parsed_custom_kws)} 件のキーワードのヒット検証")
                
                kw_hit_stats = []
                total_impact_docs = set()
                active_impact_docs = set()

                for kw in parsed_custom_kws:
                    matched_docs = [t for t in input_titles if kw in t]
                    active_docs = [t for t in active_titles if kw in t]
                    
                    total_impact_docs.update(matched_docs)
                    active_impact_docs.update(active_docs)
                    
                    is_currently_ng = kw in ngram_ng
                    is_currently_ok = kw in ngram_ok
                    
                    kw_hit_stats.append({
                        "keyword": kw,
                        "total_hits": len(matched_docs),
                        "active_hits": len(active_docs),
                        "samples": matched_docs[:15],
                        "status": "NG" if is_currently_ng else ("OK" if is_currently_ok else "未登録")
                    })

                c_s1, c_s2, c_s3 = st.columns(3)
                with c_s1:
                    st.metric("指定キーワード総数", f"{len(parsed_custom_kws)} 語")
                with c_s2:
                    st.metric("ヒットする資料総数", f"{len(total_impact_docs):,} 件", help="初期メタデータセット全体でいずれかのキーワードを含む資料数")
                with c_s3:
                    st.metric("新規除外インパクト", f"{len(active_impact_docs):,} 件", delta=f"-{len(active_impact_docs):,} 件", delta_color="inverse", help="現在まだ除外されていないデータから新たに削ぎ落とされる件数")

                c_a1, c_a2, c_a3 = st.columns([2, 2, 1])
                with c_a1:
                    if st.button(f"🚫 指定した {len(parsed_custom_kws)} 語を一括で NG (除外) ルールへ追加", type="primary", use_container_width=True, key="btn_apply_ngram_custom_ng"):
                        for kw in parsed_custom_kws:
                            ngram_ng.add(kw)
                            ngram_ok.discard(kw)
                        save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                        safe_save_json(save_dict, ngram_rules_path)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"{len(parsed_custom_kws)} 件のキーワードを NG ルールへ登録しました。")
                        st.rerun()

                with c_a2:
                    if st.button(f"✅ 指定した {len(parsed_custom_kws)} 語を一括で OK (保持) ルールへ追加", type="secondary", use_container_width=True, key="btn_apply_ngram_custom_ok"):
                        for kw in parsed_custom_kws:
                            ngram_ok.add(kw)
                            ngram_ng.discard(kw)
                        save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                        safe_save_json(save_dict, ngram_rules_path)
                        st.session_state["ngram_view_ver"] += 1
                        st.cache_data.clear()
                        st.success(f"{len(parsed_custom_kws)} 件のキーワードを OK ルールへ登録しました。")
                        st.rerun()

                with c_a3:
                    if st.button("🔄 入力クリア", use_container_width=True, key="btn_clear_ngram_custom_input"):
                        st.session_state["ngram_custom_txt_ver"] += 1
                        st.rerun()

                st.write("---")
                st.markdown("##### 📋 キーワード別ヒット詳細 ＆ 該当タイトル例")
                for stat in kw_hit_stats:
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
                                if st.button(f"🚫 『{kw}』をNGに登録", key=f"btn_cust_ng_{kw}", use_container_width=True):
                                    ngram_ng.add(kw)
                                    ngram_ok.discard(kw)
                                    save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                                    safe_save_json(save_dict, ngram_rules_path)
                                    st.session_state["ngram_view_ver"] += 1
                                    st.cache_data.clear()
                                    st.rerun()
                            else:
                                if st.button(f"↩️ 『{kw}』をNG解除", key=f"btn_cust_del_{kw}", use_container_width=True):
                                    ngram_ng.discard(kw)
                                    save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                                    safe_save_json(save_dict, ngram_rules_path)
                                    st.session_state["ngram_view_ver"] += 1
                                    st.cache_data.clear()
                                    st.rerun()

                        st.caption(f"該当するタイトルの具体例 (先頭 {len(stat['samples'])} 件):")
                        from components.file_utils import make_jps_keyword_url
                        for s in stat["samples"]:
                            jps_url = make_jps_keyword_url(s)
                            st.markdown(f"- [📖 **{s}**]({jps_url})")
            else:
                st.info("👆 上記のテキストエリアに検索・除外したい単語を入力してください（1語なら該当資料のハイライト一覧、複数語なら合算インパクトが表示されます）。")

        # ---------------------------------------------------------------------
        # TAB 2: 頻出 N-Gram パターン分析ボード (オンデマンド高速実行)
        # ---------------------------------------------------------------------
        with tab_ngram_board:
            n_options = [
                "2文字 (Bi-gram)", 
                "3文字 (Tri-gram)", 
                "4文字 (Tetra-gram)", 
                "5文字 (Penta-gram)", 
                "6文字 (Hexa-gram)", 
                "7文字 (Hepta-gram)", 
                "8文字 (Octa-gram)", 
                "9文字 (Nona-gram)"
            ]
            
            selected_n_str = st.radio("分析対象の N-gram (文字数) を選択:", options=n_options, horizontal=True, key="selected_n_gram_radio_fast")
            n_val = int(selected_n_str.split("文字")[0])

            col_o1, col_o2 = st.columns([3, 2])
            with col_o1:
                v_mode_n = st.radio(
                    f"表示オプション (N={n_val}):", 
                    options=["すべて表示", "未判定のみ", "NGのみ", "OKのみ"], 
                    horizontal=True,
                    key=f"v_mode_n_{n_val}"
                )
                is_unclassified_n_mode = (v_mode_n == "未判定のみ")
                hide_zero_ngram = st.checkbox(
                    "残存未判定件数が 0 件のパターンを非表示にする", 
                    value=True, 
                    key=f"chk_hide_zero_ngram_{n_val}"
                )
            with col_o2:
                c_mode_n = st.radio(
                    f"クリック時アクション (N={n_val}):", 
                    options=["🚫 NGに設定", "✅ OKに設定", "🔄 未判定に戻す"], 
                    horizontal=True,
                    key=f"c_mode_n_{n_val}"
                )

            items = ngram_dict.get(n_val, [])
            filtered_items = []
            for w, c, s in items:
                p_type, p_word = get_parent_rule(w, ngram_ng, ngram_ok)
                is_ng = (w in ngram_ng) or (p_type == "NG")
                is_ok = (w in ngram_ok) or (p_type == "OK")

                if v_mode_n == "未判定のみ" and (is_ng or is_ok):
                    continue
                if v_mode_n == "NGのみ" and not is_ng:
                    continue
                if v_mode_n == "OKのみ" and not is_ok:
                    continue
                filtered_items.append((w, c, s))

            active_n_samples_map = {}
            for w, c, s in filtered_items:
                # active_titles（未除外の現存タイトル群）から w を含むタイトル件数およびサンプルを正確に抽出
                valid_s = [t for t in active_titles if w in t]
                eff_c = len(valid_s)
                active_n_samples_map[w] = {
                    "eff_cnt": eff_c,
                    "samples": valid_s[:10] if valid_s else (s[:10] if isinstance(s, list) else [])
                }

            if hide_zero_ngram:
                filtered_items = [
                    (w, c, s) for w, c, s in filtered_items 
                    if active_n_samples_map.get(w, {}).get("eff_cnt", 0) > 0 or w in ngram_ng or w in ngram_ok
                ]

            if f"draft_n_{n_val}_changes" not in st.session_state:
                st.session_state[f"draft_n_{n_val}_changes"] = {}
            draft_n = st.session_state[f"draft_n_{n_val}_changes"]

            render_pill_board(
                items=filtered_items,
                active_samples_map=active_n_samples_map,
                current_ng=ngram_ng,
                current_ok=ngram_ok,
                draft_dict=draft_n,
                click_action_mode=c_mode_n,
                page_session_key=f"ngram_page_n_{n_val}",
                parent_rule_func=lambda w: get_parent_rule(w, ngram_ng, ngram_ok)
            )

        # ---------------------------------------------------------------------
        # TAB 3: 登録済ルール管理
        # ---------------------------------------------------------------------
        with tab_rules:
            st.markdown(f"### 現在の N-Gram NG / OK 登録ルール (NG: {len(ngram_ng)} 件 / OK: {len(ngram_ok)} 件)")
            cn_manage_ng, cn_manage_ok = st.columns(2)
            with cn_manage_ng:
                st.markdown(f"#### 🚫 除外(NG) N-gram パターン ({len(ngram_ng)} 件)")
                if ngram_ng:
                    n_ng_sorted = sorted(list(ngram_ng))
                    try:
                        selected_n_ng_pills = st.pills("選択して削除するパターンをクリック:", options=n_ng_sorted, selection_mode="multi", key="pills_ngram_ng")
                    except AttributeError:
                        selected_n_ng_pills = st.multiselect("削除するパターンを選択:", options=n_ng_sorted, key="ms_ngram_ng_fallback")

                    if st.button("選択パターンを NG ルールから解除", key="btn_del_n_ng_pills", type="primary", use_container_width=True):
                        if selected_n_ng_pills:
                            ngram_ng.difference_update(selected_n_ng_pills)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"{len(selected_n_ng_pills)} 件のパターンを NG ルールから削除しました。")
                            st.rerun()
                        else:
                            st.warning("解除するパターンが選択されていません。")
                else:
                    st.info("NG N-gram ルールは現在空です。")

            with cn_manage_ok:
                st.markdown(f"#### ✅ 保持(OK) N-gram パターン ({len(ngram_ok)} 件)")
                if ngram_ok:
                    n_ok_sorted = sorted(list(ngram_ok))
                    try:
                        selected_n_ok_pills = st.pills("選択して削除するパターンをクリック:", options=n_ok_sorted, selection_mode="multi", key="pills_ngram_ok")
                    except AttributeError:
                        selected_n_ok_pills = st.multiselect("削除するパターンを選択:", options=n_ok_sorted, key="ms_ngram_ok_fallback")

                    if st.button("選択パターンを OK ルールから解除", key="btn_del_n_ok_pills", type="primary", use_container_width=True):
                        if selected_n_ok_pills:
                            ngram_ok.difference_update(selected_n_ok_pills)
                            st.session_state["ngram_view_ver"] += 1
                            st.cache_data.clear()
                            st.success(f"{len(selected_n_ok_pills)} 件のパターンを OK ルールから削除しました。")
                            st.rerun()
                        else:
                            st.warning("解除するパターンが選択されていません。")
                else:
                    st.info("OK N-gram ルールは現在空です。")

