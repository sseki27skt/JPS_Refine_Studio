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
from components.guide_card import render_guide_card, render_summary_banner, render_step_navigation
from modules.ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter, clean_title_text

try:
    import streamlit_hotkeys as hotkeys
except Exception:
    hotkeys = None

try:
    from modules.duckdb_manager import DuckDBManager
except (ImportError, ValueError):
    try:
        from duckdb_manager import DuckDBManager
    except ImportError:
        DuckDBManager = None


@st.cache_data(show_spinner=False)
def load_filtered_titles(file_path, file_mtime, db_path=None, about_ng_tuple=None, exclude_types=True):
    # 1. もし about_filtered.jsonl が直接選択されている場合はそのファイルを直接読み込む (既に除外済み)
    if file_path and "about_filtered" in file_path and os.path.exists(file_path):
        titles_data = []
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
        if titles_data:
            return titles_data

    # 2. DuckDB が利用可能な場合は最優先で利用（前段の主題NGルールおよびデータ種別除外を動的に完全反映）
    if db_path and os.path.exists(db_path) and DuckDBManager is not None:
        try:
            from modules.duckdb_manager import get_duckdb_manager
            db = get_duckdb_manager(db_path) if get_duckdb_manager else DuckDBManager(db_path=db_path)
            about_ng = list(about_ng_tuple) if about_ng_tuple else None
            titles = db.get_active_titles(about_ng_keywords=about_ng, exclude_ng_types=exclude_types)
            if titles:
                return titles
        except Exception:
            pass

    # 3. フォールバック: JSONL からの直接ロード（主題NG除外を適用）
    titles_data = []
    if file_path and os.path.exists(file_path):
        about_ng_set = set(about_ng_tuple) if about_ng_tuple else set()
        about_ng_partial = [w for w in about_ng_set if len(w) >= 2]
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    # 主題NGのチェック
                    if about_ng_set:
                        a_val = item.get("schema:about", item.get("about", []))
                        a_list = a_val if isinstance(a_val, list) else [a_val]
                        kws = [k.get("schema:name", k.get("name", "")) if isinstance(k, dict) else str(k) for k in a_list]
                        if any(kw in about_ng_set or any(ng in kw for ng in about_ng_partial) for kw in kws):
                            continue
                    label_val = item.get("rdfs:label", item.get("schema:name", ""))
                    title_str = str(label_val[0]) if isinstance(label_val, list) and label_val else str(label_val)
                    titles_data.append(title_str)
                except Exception:
                    continue
    return titles_data


@st.cache_data(show_spinner=False)
def get_cached_ngrams_from_titles_fast(file_path, file_mtime, min_n=2, max_n=9, db_path=None, about_ng_tuple=None, exclude_types=True):
    titles = load_filtered_titles(file_path, file_mtime, db_path=db_path, about_ng_tuple=about_ng_tuple, exclude_types=exclude_types)
    counts = {n: Counter() for n in range(min_n, max_n + 1)}
    samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

    # 正確な全体出現数を集計（全件スキャン）
    scan_titles = titles

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


@st.cache_data(show_spinner=False)
def count_ngram_discarded_records(file_path, file_mtime, ng_rules_tuple, db_path=None, about_ng_tuple=None, exclude_types=True):
    if not ng_rules_tuple:
        return 0
    titles = load_filtered_titles(file_path, file_mtime, db_path=db_path, about_ng_tuple=about_ng_tuple, exclude_types=exclude_types)
    disc_cnt = 0
    for title in titles:
        if any(pattern in title for pattern in ng_rules_tuple):
            disc_cnt += 1
    return disc_cnt


@st.cache_data(show_spinner=False)
def get_cached_active_titles(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple=None, db_path=None, about_ng_tuple=None, exclude_types=True):
    titles = load_filtered_titles(file_path, file_mtime, db_path=db_path, about_ng_tuple=about_ng_tuple, exclude_types=exclude_types)
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


@st.cache_data(show_spinner=False)
def get_cached_active_ngram_counts(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple, n_val, db_path=None, about_ng_tuple=None, exclude_types=True):
    titles = get_cached_active_titles(file_path, file_mtime, ng_rules_tuple, ok_rules_tuple, db_path=db_path, about_ng_tuple=about_ng_tuple, exclude_types=exclude_types)
    # 正確な未判定残存数を集計（全件スキャン）
    counts = Counter()
    samples = defaultdict(list)
    scan_t = titles
    for title in scan_t:
        clean_t = clean_title_text(title)
        if len(clean_t) >= n_val:
            ngrams = set(clean_t[i:i+n_val] for i in range(len(clean_t) - n_val + 1))
            for word in ngrams:
                counts[word] += 1
                if len(samples[word]) < 10 and title not in samples[word]:
                    samples[word].append(title)
    return dict(counts), dict(samples)


def get_parent_rule(word: str, ng_set: set, ok_set: set) -> tuple:
    """
    対象文字列 word の部分文字列が ng_set / ok_set に含まれるかを最短一致で超高速判定 (O(L^2))
    """
    L = len(word)
    # 最短の部分文字列から順にチェック (親ルール優先判定)
    for sub_len in range(2, L):
        for i in range(L - sub_len + 1):
            sub = word[i:i+sub_len]
            if sub in ng_set:
                return "NG", sub
    for sub_len in range(2, L):
        for i in range(L - sub_len + 1):
            sub = word[i:i+sub_len]
            if sub in ok_set:
                return "OK", sub
    return None, None


def build_expanded_ngram_rules(ng_set, ok_set, all_ngram_dict=None):
    """
    確定した NG / OK ルール辞書を生成（不要な子パターンの自動展開を廃止しルール肥大化を防止）
    """
    rules = {}
    for ng in ng_set:
        rules[ng] = "NG"
    for ok in ok_set:
        rules[ok] = "OK"
    return rules


def render_step2b_view(paths: dict):
    """Step 2-C 画面の描画"""
    st.title("Step 2-C: タイトル語彙・文字列パターン（N-Gram / 任意キーワード）分析・除外")
    st.markdown("資料タイトルに含まれる頻出語彙（N=2〜9のN-Gram部分文字列）の集計・抽出に加え、任意の文字列・キーワードを指定した除外（NG）および合格確定（OK: LLMスキップ）ルールの作成を行います。")

    render_guide_card(
        step_num="Step 2-C",
        step_title="タイトル語彙・文字列パターン分析・除外",
        purpose="資料タイトルに出現する特徴的な語彙（N-gram接尾辞・複合語）に基づき、ノイズ資料をさらに絞り込みます。",
        impact="「画譜」「系譜」「目録」等の無関係なタイトル語彙を持つレコードが除外（NG）または合格（OK）に振り分けられます。",
        condition="タイトル語彙ルールを確定し、残った判定保留（Grey）群を次のLLMセマンティック推論に送る準備が整うこと。"
    )

    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    raw_metadata_path = paths['PATH_RAW_METADATA']
    ngram_rules_path = paths['PATH_NGRAM_RULES']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    data_dir = os.path.dirname(ngram_filtered_path)

    if not os.path.exists(raw_metadata_path):
        st.warning("対象データが存在しません。先に Step 1 で初期メタデータセットを取得してください。")
        st.stop()

    duckdb_path = paths.get('PATH_DUCKDB', os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
    input_path = raw_metadata_path

    # 前段（Step 2-B: 主題 about）の確定ルールの動的ロード（DuckDBリアルタイム連携用）
    about_rules_path = paths.get('PATH_ABOUT_RULES', os.path.join(os.path.dirname(raw_metadata_path), "rules", "about_rules.json"))
    about_ng_list = []
    if os.path.exists(about_rules_path):
        try:
            with open(about_rules_path, 'r', encoding='utf-8') as f:
                ar = json.load(f)
                about_ng_list = [k for k, v in ar.items() if v == "NG"]
        except Exception:
            about_ng_list = []
    about_ng_tuple = tuple(sorted(about_ng_list))

    # --- 前段 (Step 2-A & Step 2-B) 双方向完全自動パイプライン連動インジケーター ---
    c_pipe1, c_pipe2 = st.columns([1.5, 1.5])
    with c_pipe1:
        st.info("🔗 **Step 2-A (データ種別除外)** を自動反映して分析中")
    with c_pipe2:
        if len(about_ng_list) > 0:
            st.info(f"🔗 **Step 2-B (主題NG: {len(about_ng_list):,} 語)** を自動反映して分析中")
        else:
            st.caption("※ Step 2-B の登録ルールは現在0件です")

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

    min_n = 2
    max_n = 9

    # 全 N-gram のドラフト辞書を確実に初期化
    for n in range(min_n, max_n + 1):
        if f"draft_n_{n}_changes" not in st.session_state:
            st.session_state[f"draft_n_{n}_changes"] = {}

    all_draft_keys = [f"draft_n_{n}_changes" for n in range(min_n, max_n + 1)]
    total_draft_cnt = sum(len(st.session_state.get(k, {})) for k in all_draft_keys if isinstance(st.session_state.get(k), dict))

    use_db_ngram = bool(os.path.exists(duckdb_path) and DuckDBManager is not None)
    cur_db_p = duckdb_path if use_db_ngram else None
    cur_about_ng = about_ng_tuple if ("about_filtered" in chosen_source or chosen_source == data_source_options[0]) else None
    cur_exc_types = bool("type_filtered" in chosen_source or "about_filtered" in chosen_source or chosen_source == data_source_options[0])

    input_mtime = os.path.getmtime(input_path) if os.path.exists(input_path) else 0
    input_titles = load_filtered_titles(input_path, input_mtime, db_path=cur_db_p, about_ng_tuple=cur_about_ng, exclude_types=cur_exc_types)
    ngram_dict = get_cached_ngrams_from_titles_fast(input_path, input_mtime, min_n, max_n, db_path=cur_db_p, about_ng_tuple=cur_about_ng, exclude_types=cur_exc_types)
    total_input_records = len(input_titles)

    # 超高速インメモリ転置インデックスによるリアルタイム双方向連動 (0.001秒)
    from modules.ngram_index import get_ngram_inverted_index
    ngram_idx = get_ngram_inverted_index(tuple(input_titles))

    # 全文字条件（N=2〜9）の確定ルール＋仮設定ドラフトを完全集約
    live_ngram_ng = set(ngram_ng)
    live_ngram_ok = set(ngram_ok)
    for n in range(min_n, max_n + 1):
        d_map = st.session_state.get(f"draft_n_{n}_changes", {})
        if isinstance(d_map, dict):
            for w, st_val in d_map.items():
                if st_val == "NG":
                    live_ngram_ng.add(w)
                    live_ngram_ok.discard(w)
                elif st_val == "OK":
                    live_ngram_ok.add(w)
                    live_ngram_ng.discard(w)
                elif st_val == "RESET":
                    live_ngram_ng.discard(w)
                    live_ngram_ok.discard(w)

    # N=8等の長い語彙ルールで除外された分も全て含むリアルタイム除外タイトルID集合 (0.001秒)
    live_discarded_title_ids = ngram_idx.compute_discarded_titles(live_ngram_ng)
    ngram_discarded_records = len(live_discarded_title_ids)
    ngram_remaining_records = total_input_records - ngram_discarded_records
    ngram_reduction_rate = (ngram_discarded_records / max(1, total_input_records))

    # 全タブ・前段ステップの順序キャッシュを一括消去するヘルパー関数
    def _clear_all_ngram_order_caches():
        for n in range(min_n, max_n + 1):
            st.session_state.pop(f"ngram_order_n_{n}", None)
        st.session_state.pop("cluster_order_ids", None)
        st.session_state.pop("about_single_order", None)
        for k in list(st.session_state.keys()):
            if k.startswith("cl_kw_order_"):
                st.session_state.pop(k, None)

    # 共通の確定保存関数
    def _apply_and_save_ngram_draft():
        applied_any = False
        for dk in all_draft_keys:
            d_map = st.session_state.get(dk, {})
            if isinstance(d_map, dict) and d_map:
                for w, status in list(d_map.items()):
                    if status == "NG":
                        ngram_ng.add(w)
                        ngram_ok.discard(w)
                        applied_any = True
                    elif status == "OK":
                        ngram_ok.add(w)
                        ngram_ng.discard(w)
                        applied_any = True
                    elif status == "RESET":
                        ngram_ng.discard(w)
                        ngram_ok.discard(w)
                        applied_any = True
                d_map.clear()
        
        if applied_any:
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok)
            safe_save_json(save_dict, ngram_rules_path)
            _clear_all_ngram_order_caches()
            st.session_state["ngram_view_ver"] += 1
            st.success("判別結果を確定し ngram_rules.json へ保存しました。")
            st.rerun()

    # 3カラム / 2ペイン レイアウト（左: メイン作業領域 70% ｜ 右: 固定コントロール＆進捗パネル 30%）
    col_main, col_ctrl = st.columns([7, 3])

    # =========================================================================
    # 右側: 固定コントロール ＆ アクションパネル
    # =========================================================================
    with col_ctrl:
        st.markdown("### コントロール ＆ 進捗")

        # 1. 絞り込み進捗メトリクス
        st.markdown("##### N-Gram 絞り込み進捗")
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

        # 2. 仮選択の一括適用 ＆ 保存アクション
        st.markdown("##### ルール確定 ＆ 保存")
        if total_draft_cnt > 0:
            st.warning(f"現在 **{total_draft_cnt} 件** のパターンが仮選択中です。")
            c_dr1, c_dr2 = st.columns([3, 1.2])
            with c_dr1:
                if st.button(f"仮設定 ({total_draft_cnt} 件) を確定保存 ＆ 再ソート", type="primary", use_container_width=True, key="btn_apply_all_ngram_draft_ctrl"):
                    _apply_and_save_ngram_draft()
            with c_dr2:
                if st.button("全破棄", type="secondary", use_container_width=True, key="btn_discard_all_ngram_draft", help="すべての仮選択を取り消します。"):
                    for dk in all_draft_keys:
                        if dk in st.session_state:
                            st.session_state[dk].clear()
                    _clear_all_ngram_order_caches()
                    st.rerun()
        else:
            st.caption("すべてのルールが保存済みです。ピルをクリックすると仮選択され、確定ボタンが表示されます。")

        st.write("---")

        # 3. フィルタ適用実行（DuckDB内部高速更新でI/O待ちゼロ）
        st.markdown("##### フィルタ適用実行")
        if st.button("N-Gram フィルタを確定適用する", type="primary", use_container_width=True, key="btn_run_ngram_filter_ctrl"):
            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
            safe_save_json(save_dict, ngram_rules_path)

            if use_db_ngram:
                with st.spinner("DuckDB 内で N-Gram ルールを即時適用中..."):
                    db = DuckDBManager(db_path=duckdb_path)
                    about_rules = {}
                    if os.path.exists(about_rules_path):
                        try:
                            with open(about_rules_path, 'r', encoding='utf-8') as f:
                                about_rules = json.load(f)
                        except Exception:
                            pass
                    res = db.apply_rules_fast(about_rules, save_dict)
                    db.close()
                    st.session_state["_pipeline_metrics_sig"] = None
                    passed = res.get("ok", 0) + res.get("grey", 0)
                    disc = res.get("ng", 0)
            else:
                passed, disc = 0, 0

            _clear_all_ngram_order_caches()
            st.session_state["ngram_view_ver"] += 1
            st.success(f"N-Gram ルールを確定適用しました（残存見込: {passed:,} 件 / 除外: {disc:,} 件）")
            st.rerun()

        # Step 2-B へのクイック遷移ボタン（ドラフト自動保存付き）
        if st.button("⬅ Step 2-B (主題キーワード分析) へ戻る", use_container_width=True, key="btn_nav_back_to_step2b"):
            if total_draft_cnt > 0:
                _apply_and_save_ngram_draft()
            st.session_state["nav_target"] = "Step 2-B: 主題 (schema:about) キーワード分析・判別"
            st.rerun()

        st.write("---")

        # 4. 初期化
        with st.popover("ルール全初期化", help="N-Gramルールを初期化"):
            st.warning("N-Gram ルール (ngram_rules.json) を全初期化しますか？")
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
            "タイトルキーワード検索 ＆ 一括除外",
            "頻出 N-Gram パターン分析 (N=2〜9)",
            f"登録済ルール ({len(ngram_ng)} NG / {len(ngram_ok)} OK)"
        ])

        # ---------------------------------------------------------------------
        # TAB 1: タイトルキーワード検索 ＆ 一括除外 (単語検索・複数一括の両対応)
        # ---------------------------------------------------------------------
        with tab_search:
            st.markdown("### タイトルキーワード検索 ＆ 一括除外・保持指定")
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
                        is_active = (idx not in live_discarded_title_ids)
                        matched_records.append({
                            "title": t,
                            "is_active": is_active
                        })

                tot_hit = len(matched_records)
                act_hit = sum(1 for r in matched_records if r["is_active"])

                is_q_ng = kw_q in ngram_ng
                is_q_ok = kw_q in ngram_ok
                if is_q_ng:
                    cur_status_badge = "[NGルール登録済]"
                elif is_q_ok:
                    cur_status_badge = "[OKルール登録済]"
                else:
                    cur_status_badge = "[未登録]"

                st.markdown(f"#### 『**{kw_q}**』のヒット結果: 全 **{tot_hit:,}** 件 （未除外残存: **{act_hit:,}** 件） ｜ {cur_status_badge}")
                st.markdown(make_rich_search_links_md(kw_q))

                # アクションボタン
                c_act_b1, c_act_b2, c_act_b3 = st.columns([2, 2, 1])
                with c_act_b1:
                    if not is_q_ng:
                        if st.button(f"『{kw_q}』を NG (除外) ルールに追加", type="primary", use_container_width=True, key=f"btn_add_uni_ng_{kw_q}"):
                            ngram_ng.add(kw_q)
                            ngram_ok.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"『{kw_q}』を NG ルールへ登録しました (ヒット {tot_hit:,} 件が除外対象になります)。")
                            st.rerun()
                    else:
                        if st.button(f"『{kw_q}』の NG 登録を解除", use_container_width=True, key=f"btn_rm_uni_ng_{kw_q}"):
                            ngram_ng.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"『{kw_q}』の NG 登録を解除しました。")
                            st.rerun()

                with c_act_b2:
                    if not is_q_ok:
                        if st.button(f"『{kw_q}』を OK (保持) ルールに追加", type="secondary", use_container_width=True, key=f"btn_add_uni_ok_{kw_q}"):
                            ngram_ok.add(kw_q)
                            ngram_ng.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"『{kw_q}』を OK ルールへ登録しました。")
                            st.rerun()
                    else:
                        if st.button(f"『{kw_q}』の OK 登録を解除", use_container_width=True, key=f"btn_rm_uni_ok_{kw_q}"):
                            ngram_ok.discard(kw_q)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"『{kw_q}』の OK 登録を解除しました。")
                            st.rerun()

                with c_act_b3:
                    if st.button("クリア", use_container_width=True, key="btn_clear_uni_single"):
                        st.session_state["ngram_custom_txt_ver"] += 1
                        st.rerun()

                st.write("---")
                st.caption("該当タイトル一覧 (全件スクロール確認可能):")

                with st.container(height=450):
                    if not matched_records:
                        st.info("条件に一致する資料はありません。")
                    
                    max_disp_d = min(tot_hit, 300)
                    for item in matched_records[:max_disp_d]:
                        raw_t = item["title"]
                        act_tag = "" if item["is_active"] else " <span class='status-badge status-badge-neutral'>[既除外]</span>"
                        
                        from components.file_utils import make_jps_keyword_url
                        hl_t = re.sub(
                            re.escape(kw_q), 
                            f"<mark class='status-badge status-badge-reject'>{kw_q}</mark>", 
                            raw_t, 
                            flags=re.IGNORECASE
                        )
                        jps_link = make_jps_keyword_url(raw_t)
                        
                        st.markdown(f"• [**{hl_t}**]({jps_link}){act_tag}", unsafe_allow_html=True)

                    if tot_hit > max_disp_d:
                        st.caption(f"※ パフォーマンス保護のため現在上位 {max_disp_d} 件を表示しています。")

            elif len(parsed_custom_kws) > 1:
                # -------------------------------------------------------------
                # 【複数キーワード入力時】: 合算インパクト＆バッチ一括登録ビュー
                # -------------------------------------------------------------
                st.markdown(f"#### 入力された {len(parsed_custom_kws)} 件のキーワードのヒット検証")
                
                kw_hit_stats = []
                total_impact_docs = set()
                active_impact_docs = set()

                for kw in parsed_custom_kws:
                    kw_lower = kw.lower()
                    matched_ids = [idx for idx, t in enumerate(input_titles) if kw_lower in t.lower()]
                    active_ids = [idx for idx in matched_ids if idx not in live_discarded_title_ids]
                    matched_docs = [input_titles[idx] for idx in matched_ids]
                    active_docs = [input_titles[idx] for idx in active_ids]
                    
                    total_impact_docs.update(matched_ids)
                    active_impact_docs.update(active_ids)
                    
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
                    if st.button(f"指定した {len(parsed_custom_kws)} 語を一括で NG (除外) ルールへ追加", type="primary", use_container_width=True, key="btn_apply_ngram_custom_ng"):
                        for kw in parsed_custom_kws:
                            ngram_ng.add(kw)
                            ngram_ok.discard(kw)
                        save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                        safe_save_json(save_dict, ngram_rules_path)
                        _clear_all_ngram_order_caches()
                        st.session_state["ngram_view_ver"] += 1
                        st.success(f"{len(parsed_custom_kws)} 件のキーワードを NG ルールへ登録しました。")
                        st.rerun()

                with c_a2:
                    if st.button(f"指定した {len(parsed_custom_kws)} 語を一括で OK (保持) ルールへ追加", type="secondary", use_container_width=True, key="btn_apply_ngram_custom_ok"):
                        for kw in parsed_custom_kws:
                            ngram_ok.add(kw)
                            ngram_ng.discard(kw)
                        save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                        safe_save_json(save_dict, ngram_rules_path)
                        _clear_all_ngram_order_caches()
                        st.session_state["ngram_view_ver"] += 1
                        st.success(f"{len(parsed_custom_kws)} 件のキーワードを OK ルールへ登録しました。")
                        st.rerun()

                with c_a3:
                    if st.button("入力クリア", use_container_width=True, key="btn_clear_ngram_custom_input"):
                        st.session_state["ngram_custom_txt_ver"] += 1
                        st.rerun()

                st.write("---")
                st.markdown("##### キーワード別ヒット詳細 ＆ 該当タイトル例")
                for stat in kw_hit_stats:
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
                                if st.button(f"『{kw}』をNGに登録", key=f"btn_cust_ng_{kw}", use_container_width=True):
                                    ngram_ng.add(kw)
                                    ngram_ok.discard(kw)
                                    save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                                    safe_save_json(save_dict, ngram_rules_path)
                                    _clear_all_ngram_order_caches()
                                    st.session_state["ngram_view_ver"] += 1
                                    st.rerun()
                            else:
                                if st.button(f"『{kw}』のNG解除", key=f"btn_cust_del_{kw}", use_container_width=True):
                                    ngram_ng.discard(kw)
                                    save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok, ngram_dict)
                                    safe_save_json(save_dict, ngram_rules_path)
                                    _clear_all_ngram_order_caches()
                                    st.session_state["ngram_view_ver"] += 1
                                    st.rerun()

                        st.caption(f"該当するタイトルの具体例 (先頭 {len(stat['samples'])} 件):")
                        from components.file_utils import make_jps_keyword_url
                        for s in stat["samples"]:
                            jps_url = make_jps_keyword_url(s)
                            st.markdown(f"- [**{s}**]({jps_url})")
            else:
                st.info("上記のテキストエリアに検索・除外したい単語を入力してください（1語なら該当資料のハイライト一覧、複数語なら合算インパクトが表示されます）。")

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
                c_sub1, c_sub2 = st.columns([3, 2])
                with c_sub1:
                    sort_mode_n = st.radio(
                        "並び順:",
                        options=["未判定影響度順", "全体出現頻度順"],
                        horizontal=True,
                        key=f"sort_mode_n_{n_val}",
                        help="未判定影響度順: 現在の未除外データの中で多くヒットする（フィルタリング影響の大きい）順に並べます。"
                    )
                with c_sub2:
                    hide_zero_ngram = st.checkbox(
                        "残存未判定 0 件を非表示", 
                        value=True, 
                        key=f"chk_hide_zero_ngram_{n_val}"
                    )
            with col_o2:
                c_mode_n = st.radio(
                    f"クリック時アクション (N={n_val}):", 
                    options=["❌ [除外] NGに設定", "✅ [保持] OKに設定", "❔ 未判定に戻す"], 
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

            if f"draft_n_{n_val}_changes" not in st.session_state:
                st.session_state[f"draft_n_{n_val}_changes"] = {}
            draft_n = st.session_state[f"draft_n_{n_val}_changes"]

            # 表示対象候補語彙のリスト
            target_words = [item[0] for item in filtered_items]

            # 1. 基本の残存件数集計 (0.001秒)
            realtime_active_counts = ngram_idx.compute_remaining_counts(target_words, live_discarded_title_ids)
            
            # 確定済みルールのみに対する基準件数（自己除外前の真の影響度）
            comm_discarded_ids = ngram_idx.compute_discarded_titles(ngram_ng)
            comm_active_counts = ngram_idx.compute_remaining_counts(target_words, comm_discarded_ids)

            # 2. 【最重要】自分自身が仮除外されたことで自分自身のピルが0件扱いになり吹っ飛ぶのを防止
            # 現在のタブで仮設定中の語彙については、自己除外前の本来の未判定影響度件数を保持
            for dw in draft_n:
                if dw in target_words:
                    realtime_active_counts[dw] = comm_active_counts.get(dw, 0)

            active_n_samples_map = {}
            for w, c, s in filtered_items:
                eff_c = min(realtime_active_counts.get(w, 0), c)
                active_n_samples_map[w] = {
                    "eff_cnt": eff_c,
                    "samples": s[:10] if isinstance(s, list) else []
                }

            # 3. 確定保存＆再ソートが押されるまでは、現在のタブの表示ピル集合と順序を完全に固定（クリック時のレイアウトシフト・消失を根絶！）
            order_key = f"ngram_order_n_{n_val}"
            last_sort_key = f"last_sort_mode_{n_val}"
            last_hide_zero_key = f"last_hide_zero_{n_val}"
            if (st.session_state.get(last_sort_key) != sort_mode_n or 
                st.session_state.get(last_hide_zero_key) != hide_zero_ngram):
                st.session_state.pop(order_key, None)
                st.session_state[last_sort_key] = sort_mode_n
                st.session_state[last_hide_zero_key] = hide_zero_ngram

            if order_key not in st.session_state:
                initial_items = list(filtered_items)
                if hide_zero_ngram:
                    # 初回整列時のみ残存0件を候補から除外
                    initial_items = [
                        it for it in initial_items 
                        if active_n_samples_map.get(it[0], {}).get("eff_cnt", 0) > 0 or it[0] in draft_n or it[0] in ngram_ng or it[0] in ngram_ok
                    ]
                if sort_mode_n == "未判定影響度順":
                    initial_items.sort(
                        key=lambda item: (
                            active_n_samples_map.get(item[0], {}).get("eff_cnt", 0),
                            item[1]
                        ),
                        reverse=True
                    )
                else:
                    initial_items.sort(key=lambda item: item[1], reverse=True)
                st.session_state[order_key] = [item[0] for item in initial_items]

            # 固定された表示順序とピル集合を復元（ドラフト編集中はピルが消えたり動いたりしない）
            order_words = st.session_state[order_key]
            item_map = {item[0]: item for item in filtered_items}
            display_items = []
            for w in order_words:
                if w not in item_map:
                    continue
                eff_cnt = active_n_samples_map.get(w, {}).get("eff_cnt", 0)
                # 残存未判定0件を非表示にする設定の時：
                # 他の条件（長いN-gram除外や主題除外）により未判定残存件数が0になったピルは絶対に非表示にする！
                # ただし、操作中の仮設定ピル（w in draft_n）や確定済みピル（w in ngram_ng or w in ngram_ok）は表示を維持
                if hide_zero_ngram and eff_cnt == 0 and w not in draft_n and w not in ngram_ng and w not in ngram_ok:
                    continue
                display_items.append(item_map[w])

            # インパクトメトリクス情報の構築 (現在の文字数タブで仮選択がある場合)
            n_draft_cnt = len(draft_n)
            impact_metrics_n = {
                "discarded_delta": max(0, ngram_discarded_records - len(comm_discarded_ids)),
                "remaining_count": ngram_remaining_records
            } if n_draft_cnt > 0 else None

            render_pill_board(
                items=display_items,
                active_samples_map=active_n_samples_map,
                current_ng=ngram_ng,
                current_ok=ngram_ok,
                draft_dict=draft_n,
                click_action_mode=c_mode_n,
                page_session_key=f"ngram_page_n_{n_val}",
                parent_rule_func=lambda w: get_parent_rule(w, ngram_ng, ngram_ok),
                on_confirm_save=_apply_and_save_ngram_draft,
                impact_metrics=impact_metrics_n
            )

        # ---------------------------------------------------------------------
        # TAB 3: 登録済ルール管理
        # ---------------------------------------------------------------------
        with tab_rules:
            st.markdown(f"### 現在の N-Gram NG / OK 登録ルール (NG: {len(ngram_ng)} 件 / OK: {len(ngram_ok)} 件)")

            # 冗長ルールの自動クリーンアップツール
            with st.expander("登録ルールの最適化・冗長パターン一括クリーンアップ", expanded=False):
                st.caption("より短い親パターン（例:『楽譜』）が既にNGになっている場合、それを含む長い子パターン（例:『大日本楽譜集』）は重複しており不要です。これらを整理してルールファイルを大幅に軽量化・高速化します。")
                if st.button("冗長な子パターンを自動整理してスリム化", key="btn_clean_redundant_rules"):
                    ng_sorted = sorted(list(ngram_ng), key=len)
                    minimal_ng = set()
                    for w in ng_sorted:
                        covered = any(sub in w for sub in minimal_ng)
                        if not covered:
                            minimal_ng.add(w)
                    removed_cnt = len(ngram_ng) - len(minimal_ng)
                    ngram_ng.clear()
                    ngram_ng.update(minimal_ng)
                    save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok)
                    safe_save_json(save_dict, ngram_rules_path)
                    st.session_state["ngram_view_ver"] += 1
                    st.success(f"重複・冗長な {removed_cnt:,} 件のパターンを整理しました（現在 {len(ngram_ng):,} 件）。")
                    st.rerun()

            cn_manage_ng, cn_manage_ok = st.columns(2)
            with cn_manage_ng:
                st.markdown(f"#### 除外 (NG) N-gram パターン ({len(ngram_ng)} 件)")
                if ngram_ng:
                    search_ng = st.text_input("NGパターン内を検索:", key="txt_search_ng_pills", placeholder="絞り込みキーワードを入力...")
                    n_ng_sorted = sorted(list(ngram_ng))
                    if search_ng:
                        disp_ng_list = [w for w in n_ng_sorted if search_ng.lower() in w.lower()]
                    else:
                        disp_ng_list = n_ng_sorted[:80]

                    st.caption(f"表示中: {len(disp_ng_list)} 件 / 全 {len(ngram_ng)} 件" + (" (上位80件を表示中、検索で絞り込めます)" if not search_ng and len(n_ng_sorted) > 80 else ""))

                    try:
                        selected_n_ng_pills = st.pills("解除するパターンを選択:", options=disp_ng_list, selection_mode="multi", key="pills_ngram_ng")
                    except AttributeError:
                        selected_n_ng_pills = st.multiselect("解除するパターンを選択:", options=disp_ng_list, key="ms_ngram_ng_fallback")

                    if st.button("選択パターンを NG ルールから解除", key="btn_del_n_ng_pills", type="primary", use_container_width=True):
                        if selected_n_ng_pills:
                            ngram_ng.difference_update(selected_n_ng_pills)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"{len(selected_n_ng_pills)} 件のパターンを NG ルールから削除しました。")
                            st.rerun()
                        else:
                            st.warning("解除するパターンが選択されていません。")
                else:
                    st.info("NG N-gram ルールは現在空です。")

            with cn_manage_ok:
                st.markdown(f"#### 保持 (OK) N-gram パターン ({len(ngram_ok)} 件)")
                if ngram_ok:
                    search_ok = st.text_input("OKパターン内を検索:", key="txt_search_ok_pills", placeholder="絞り込みキーワードを入力...")
                    n_ok_sorted = sorted(list(ngram_ok))
                    if search_ok:
                        disp_ok_list = [w for w in n_ok_sorted if search_ok.lower() in w.lower()]
                    else:
                        disp_ok_list = n_ok_sorted[:80]

                    st.caption(f"表示中: {len(disp_ok_list)} 件 / 全 {len(ngram_ok)} 件" + (" (上位80件を表示中、検索で絞り込めます)" if not search_ok and len(n_ok_sorted) > 80 else ""))

                    try:
                        selected_n_ok_pills = st.pills("解除するパターンを選択:", options=disp_ok_list, selection_mode="multi", key="pills_ngram_ok")
                    except AttributeError:
                        selected_n_ok_pills = st.multiselect("解除するパターンを選択:", options=disp_ok_list, key="ms_ngram_ok_fallback")

                    if st.button("選択パターンを OK ルールから解除", key="btn_del_n_ok_pills", type="primary", use_container_width=True):
                        if selected_n_ok_pills:
                            ngram_ok.difference_update(selected_n_ok_pills)
                            save_dict = build_expanded_ngram_rules(ngram_ng, ngram_ok)
                            safe_save_json(save_dict, ngram_rules_path)
                            st.session_state["ngram_view_ver"] += 1
                            st.success(f"{len(selected_n_ok_pills)} 件のパターンを OK ルールから削除しました。")
                            st.rerun()
                        else:
                            st.warning("解除するパターンが選択されていません。")
                else:
                    st.info("OK N-gram ルールは現在空です。")

    # 最下部ナビゲーション
    render_step_navigation(
        prev_choice="Step 2-B: 主題 (schema:about) キーワード分析・判別",
        next_choice="Step 3: LLMセマンティック適合判定 (判定保留群の分類)"
    )

