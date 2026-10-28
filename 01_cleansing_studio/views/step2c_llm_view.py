# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 3: LLMセマンティック適合判定ビュー
事前ルールフィルタ（Step 2-A〜C）で確定しなかった判定保留（グレーゾーン）データを抽出し、
LLMによるテキスト解釈と根拠理由生成に基づくセマンティック適合判定を行います。
"""
import json
import os
import time
import pandas as pd
import streamlit as st

from components.file_utils import count_lines
from components.guide_card import render_guide_card, render_summary_banner, render_step_navigation
from modules.rule_filter import split_dataset_by_rules
from modules.llm_classifier import run_llm_semantic_classification, run_stage2_llm_classification

try:
    from modules.duckdb_manager import DuckDBManager
except (ImportError, ValueError):
    try:
        from duckdb_manager import DuckDBManager
    except ImportError:
        DuckDBManager = None

def render_step2c_view(paths: dict):
    """Step 3 画面の描画"""
    st.title("Step 3: LLMセマンティック適合判定 (判定保留群の分類)")
    st.caption("事前ルールフィルタで確定しなかった判定保留（グレーゾーン）データを抽出し、LLMによるテキスト解釈と根拠理由生成に基づくセマンティック適合判定を行います。")

    render_guide_card(
        step_num="Step 3",
        step_title="LLMセマンティック適合判定 (判定保留群の分類)",
        purpose="ルールでは白黒つかなかった判定保留（Grey）資料に対し、LLMを用いて解説文・解題等の文脈から適合性を判定します。",
        impact="Grey群のレコードにLLMによる合格/除外および推論根拠（Reasoning）が付与されます。",
        condition="保留群のLLM分類推論を実行し、全件の自動判定結果が得られること（または推論をスキップして専門家査読へ進むこと）。"
    )

    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    raw_metadata_path = paths['PATH_RAW_METADATA']
    about_rules_path = paths['PATH_ABOUT_RULES']
    ngram_rules_path = paths['PATH_NGRAM_RULES']
    target_for_llm_path = paths['PATH_TARGET_FOR_LLM']
    confirmed_ok_path = paths['PATH_CONFIRMED_OK']
    discarded_rules_path = paths['PATH_DISCARDED_RULES']
    llm_judgments_path = paths['PATH_LLM_JUDGMENTS']
    data_dir = os.path.dirname(llm_judgments_path)

    # 入力データソースの決定 (Step 2-C > Step 2-B > Step 2-A > Raw)
    raw_input_path = ngram_filtered_path if os.path.exists(ngram_filtered_path) else (
        about_filtered_path if os.path.exists(about_filtered_path) else (
            type_filtered_path if os.path.exists(type_filtered_path) else raw_metadata_path
        )
    )
    if not os.path.exists(raw_input_path):
        st.warning("対象データが存在しません。先に Step 1 または Step 2 を実行してください。")
        st.stop()

    def _calc_rules_sig():
        sig = []
        for p in [about_rules_path, ngram_rules_path, paths.get('PATH_TYPE_RULES')]:
            if p and os.path.exists(p):
                sig.append((p, os.path.getmtime(p), os.path.getsize(p)))
            else:
                sig.append((p, 0, 0))
        return tuple(sig)

    current_rules_sig = _calc_rules_sig()
    cached_rules_sig = st.session_state.get("_step2c_rules_sig")
    needs_split = (cached_rules_sig != current_rules_sig) or (not os.path.exists(target_for_llm_path))

    duckdb_path = paths.get("PATH_DUCKDB", os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
    has_duckdb_llm = bool(DuckDBManager and os.path.exists(duckdb_path))

    def do_split():
        if has_duckdb_llm:
            try:
                with st.spinner("DuckDB 高速エンジンで最新ルール仕分けを即時計算中..."):
                    db = DuckDBManager(db_path=duckdb_path)
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
                    res = db.apply_rules_fast(about_rules, ngram_rules)
                    # LLM推論対象（Grey群）のみをストリーミング書き出し
                    grey_c = db.export_intermediate_jsonl('target_for_llm', target_for_llm_path) if hasattr(db, 'export_intermediate_jsonl') else 0
                    if grey_c == 0:
                        _, _, grey_c = db.export_split_datasets(
                            output_target_for_llm_jsonl=target_for_llm_path,
                            output_confirmed_ok_jsonl=confirmed_ok_path,
                            output_discarded_csv=None
                        )
                    db.close()
                    st.session_state["_step2c_rules_sig"] = current_rules_sig
                    st.session_state["_pipeline_metrics_sig"] = None
                    return res.get("ok", 0), res.get("ng", 0), res.get("grey", 0)
            except Exception as e:
                pass

        with st.spinner("ルールに基づいてデータを仕分け中 (OK合格 / NG除外 / グレーゾーン)..."):
            ok_c, ng_c, grey_c = split_dataset_by_rules(
                input_jsonl_path=raw_input_path,
                about_rules_path=about_rules_path,
                ngram_rules_path=ngram_rules_path,
                output_target_for_llm_jsonl=target_for_llm_path,
                output_confirmed_ok_jsonl=confirmed_ok_path,
                output_discarded_csv=None
            )
            st.session_state["_step2c_rules_sig"] = current_rules_sig
            return ok_c, ng_c, grey_c

    # ルール更新検知またはファイル未生成時のみ自動実行
    if needs_split:
        ok_rules_cnt, ng_rules_cnt, grey_cnt = do_split()
    else:
        if has_duckdb_llm:
            try:
                db_cnt = DuckDBManager(db_path=duckdb_path)
                p_stats = db_cnt.get_prisma_flow_stats()
                db_cnt.close()
                ok_rules_cnt = p_stats.get("rule_ok", 0)
                ng_rules_cnt = p_stats.get("rule_ng", 0) + p_stats.get("type_discarded", 0)
                grey_cnt = p_stats.get("rule_grey", 0)
            except Exception:
                ok_rules_cnt = count_lines(confirmed_ok_path) if os.path.exists(confirmed_ok_path) else 0
                ng_rules_cnt = 0
                grey_cnt = count_lines(target_for_llm_path) if os.path.exists(target_for_llm_path) else 0
        else:
            ok_rules_cnt = count_lines(confirmed_ok_path) if os.path.exists(confirmed_ok_path) else 0
            ng_rules_cnt = 0
            grey_cnt = count_lines(target_for_llm_path) if os.path.exists(target_for_llm_path) else 0

    # ステータス表示
    st.markdown("### 事前ルールフィルタによる仕分け状況 (DuckDB 自動同期)")
    c_flt1, c_flt2, c_flt3, c_flt_act = st.columns([2.5, 2.5, 2.5, 2.5])
    with c_flt1:
        st.metric("ルール適合 (LLMバイパス)", f"{ok_rules_cnt:,} 件", help="About/タイトルルールでOK判定されたためLLM判定をスキップ")
    with c_flt2:
        st.metric("ルール除外 (事前除外)", f"{ng_rules_cnt:,} 件", help="About/タイトルルールでNG判定されたため事前除外")
    with c_flt3:
        st.metric("LLM判定対象 (判定保留群)", f"{grey_cnt:,} 件", help="判定保留のデータ。これらのみがLLMへ投入されます。")
    with c_flt_act:
        if st.button("手動で再同期 ＆ 再仕分け", help="Step 2の最新ルールを強制的に反映して仕分けファイルを再作成します", use_container_width=True):
            ok_rules_cnt, ng_rules_cnt, grey_cnt = do_split()
            st.success(f"最新ルールで同期完了 (保留: {grey_cnt:,} 件)")
            st.rerun()

    cfg = st.session_state.get("llm_config", {})
    provider_name = cfg.get('provider', 'gemini')
    model_name = cfg.get('model', 'gemini-3.6-flash')
    default_domain_def = st.session_state.get("expansion_res", {}).get("domain_definition", "日本の古典籍における楽譜・音楽資料")

    with st.expander("セマンティック判定パラメータおよびLLM接続設定", expanded=True):
        domain_def = st.text_area(
            "対象ドメイン定義 (LLM判定基準):",
            value=default_domain_def,
            height=70,
            help="LLMが適合判定を行うためのドメイン評価基準テキスト"
        )
        c_cfg1, c_cfg2 = st.columns(2)
        with c_cfg1:
            st.markdown(f"- **LLMプロバイダー**: `{provider_name}`")
            st.markdown(f"- **使用モデル**: `{model_name}`")
        with c_cfg2:
            limit_val = st.number_input("LLM判定処理件数の上限 (テスト実行用):", min_value=5, max_value=5000, value=min(grey_cnt, 50) if grey_cnt > 0 else 30, step=10)
            workers_val = st.slider("並列スレッド数 (ThreadPool):", min_value=1, max_value=8, value=4)

    # 停止フラグのセッション状態
    if "stop_llm_flag" not in st.session_state:
        st.session_state["stop_llm_flag"] = False

    c_btn1, c_btn2, c_btn3 = st.columns([3, 1.5, 1])
    with c_btn1:
        start_llm_btn = st.button("LLMによるセマンティック適合判定の実行", type="primary", use_container_width=True)
    with c_btn2:
        stop_llm_btn = st.button("判定処理の中断", type="secondary", use_container_width=True, help="実行中のLLM判定処理を中断し、そこまでの判定結果を保存します。")
    with c_btn3:
        reset_llm_btn = st.button("LLM判定ログの初期化", use_container_width=True, help="これまでのLLM判定結果ログを消去します。")

    if stop_llm_btn:
        st.session_state["stop_llm_flag"] = True
        st.warning("停止シグナルを送信しました。現在のデータ判定完了後に処理を中断します。")

    if reset_llm_btn:
        st.session_state["confirm_reset_llm"] = True

    if st.session_state.get("confirm_reset_llm", False):
        with st.container(border=True):
            st.warning("これまでに推論・蓄積されたLLM判定結果ログをすべて初期化（消去）しますか？この操作は取り消せません。")
            c_rc1, c_rc2 = st.columns([1, 1])
            with c_rc1:
                if st.button("はい、判定ログを初期化します", type="primary", use_container_width=True, key="btn_confirm_reset_llm_yes"):
                    for p in [llm_judgments_path, f"{data_dir}/tmp_llm_grey_judgments.jsonl"]:
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                    st.cache_data.clear()
                    st.session_state["stop_llm_flag"] = False
                    st.session_state["confirm_reset_llm"] = False
                    st.success("LLM判定結果ログを初期化しました。")
                    st.rerun()
            with c_rc2:
                if st.button("キャンセル", use_container_width=True, key="btn_cancel_reset_llm"):
                    st.session_state["confirm_reset_llm"] = False
                    st.rerun()

    if start_llm_btn:
        st.session_state["stop_llm_flag"] = False
        if grey_cnt == 0:
            st.info("LLM判定対象の判定保留データがありません（全件判定済み）。")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            def should_stop_check():
                return st.session_state.get("stop_llm_flag", False)

            def on_progress(current, total, title, is_target, reason):
                progress_bar.progress(current / total)
                badge = "[適合]" if is_target is True else ("[非適合]" if is_target is False else "[不明]")
                status_text.markdown(f"進捗: **{current}/{total}** | {badge} **{title[:35]}** : *{reason}*")

            tmp_llm_out = f"{data_dir}/tmp_llm_grey_judgments.jsonl"

            acc, rej, unk, tot_items, unique_cnt = run_llm_semantic_classification(
                input_jsonl_path=target_for_llm_path,
                output_judgments_path=tmp_llm_out,
                domain_definition=domain_def,
                provider=provider_name,
                api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                api_key=cfg.get("api_key", ""),
                model=model_name,
                limit=limit_val,
                max_workers=workers_val,
                progress_callback=on_progress,
                should_stop=should_stop_check
            )

            merged_judgments = []
            if os.path.exists(confirmed_ok_path):
                with open(confirmed_ok_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if line.strip():
                            try:
                                merged_judgments.append(json.loads(line))
                            except Exception:
                                pass

            if os.path.exists(tmp_llm_out):
                with open(tmp_llm_out, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if line.strip():
                            try:
                                merged_judgments.append(json.loads(line))
                            except Exception:
                                pass

            with open(llm_judgments_path, 'w', encoding='utf-8') as f:
                for r in merged_judgments:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

            duckdb_path = paths.get("PATH_DUCKDB", os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
            if DuckDBManager and os.path.exists(duckdb_path):
                try:
                    db_sync = DuckDBManager(duckdb_path)
                    db_sync.sync_llm_judgments(llm_judgments_path)
                    db_sync.close()
                except Exception:
                    pass

            if st.session_state.get("stop_llm_flag", False):
                st.warning(f"LLM判定処理を途中で停止しました。(途中判定結果: 適合 {acc} 件 / 非適合 {rej} 件 / 不明 {unk} 件 を保存)")
            else:
                st.success(f"LLMセマンティック判定完了 (適合: {acc:,} 件 / 非適合: {rej:,} 件 / 判定不能: {unk:,} 件)")
            time.sleep(1)
            st.rerun()

    if os.path.exists(llm_judgments_path) and os.path.getsize(llm_judgments_path) > 0:
        st.markdown("---")
        st.subheader("Stage 2: 判定不能 (UNKNOWN) データのWeb情報補強再判定")
        st.caption("Stage 1 で判定不能となったデータに対し、外部Web情報を自動参照して再判定を行います。")

        unk_count = 0
        total_judged = 0
        with open(llm_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    total_judged += 1
                    try:
                        data = json.loads(line)
                        if data.get("is_target") is None:
                            unk_count += 1
                    except Exception:
                        pass

        c_stg1, c_stg2 = st.columns(2)
        with c_stg1:
            st.metric("判定対象データ総数", f"{total_judged:,} 件 (ルール適合 {ok_rules_cnt:,} 件含む)")
        with c_stg2:
            st.metric("判定不能 (UNKNOWN) データ数", f"{unk_count:,} 件", delta=f"{unk_count:,} 件の再判定が可能", delta_color="inverse")

        if unk_count > 0:
            c_stg_btn1, c_stg_btn2 = st.columns([3, 1])
            with c_stg_btn1:
                start_st2_btn = st.button("Stage 2: 判定不能 (UNKNOWN) データの情報補強再判定の実行", type="primary", use_container_width=True)
            with c_stg_btn2:
                stop_st2_btn = st.button("Stage 2 中断", type="secondary", use_container_width=True, key="btn_stop_st2")

            if stop_st2_btn:
                st.session_state["stop_llm_flag"] = True
                st.warning("停止シグナルを送信しました。")

            if start_st2_btn:
                st.session_state["stop_llm_flag"] = False
                st2_progress_bar = st.progress(0)
                st2_status_text = st.empty()

                def should_stop_check():
                    return st.session_state.get("stop_llm_flag", False)

                def on_st2_progress(current, total, title, is_target, reason):
                    st2_progress_bar.progress(current / total)
                    badge = "[適合]" if is_target is True else ("[非適合]" if is_target is False else "[不明]")
                    st2_status_text.markdown(f"Stage 2 進捗: **{current}/{total}** 件 | {badge} **{title[:35]}** : *{reason}*")

                resolved_acc, resolved_rej, rem_unk = run_stage2_llm_classification(
                    judgments_jsonl_path=llm_judgments_path,
                    domain_definition=domain_def,
                    provider=provider_name,
                    api_base=cfg.get("api_base", "http://localhost:1234/v1"),
                    api_key=cfg.get("api_key", ""),
                    model=model_name,
                    max_workers=min(2, workers_val),
                    progress_callback=on_st2_progress,
                    should_stop=should_stop_check
                )

                duckdb_path = paths.get("PATH_DUCKDB", os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
                if DuckDBManager and os.path.exists(duckdb_path):
                    try:
                        db_sync = DuckDBManager(duckdb_path)
                        db_sync.sync_llm_judgments(llm_judgments_path)
                        db_sync.close()
                    except Exception:
                        pass

                if st.session_state.get("stop_llm_flag", False):
                    st.warning(f"Stage 2 補強再判定を途中で停止しました。(途中結果: 新規適合 {resolved_acc} 件 / 新規非適合 {resolved_rej} 件)")
                else:
                    st.success(f"Stage 2 補強再判定完了 (新規適合: {resolved_acc} 件 / 新規非適合: {resolved_rej} 件 / 残り判定不能: {rem_unk} 件)")
                time.sleep(1)
                st.rerun()
        else:
            st.info("現在、判定不能 (UNKNOWN) のデータはありません。")

        st.markdown("---")
        with st.expander("LLM判定結果および参照Web情報の確認・検証", expanded=True):
            if os.path.exists(llm_judgments_path) and os.path.getsize(llm_judgments_path) > 0:
                c_flt_t, c_flt_s, c_flt_q = st.columns(3)
                with c_flt_t:
                    filter_status = st.selectbox("判定結果で絞り込み:", ["すべて", "適合 (true)のみ", "非適合 (false)のみ", "判定不能 (null)のみ"], key="llm_flt_status")
                with c_flt_s:
                    filter_source = st.selectbox("判定ソースで絞り込み:", ["すべて", "Web情報補強 LLM判定", "ルール適合パス (LLMバイパス)"], key="llm_flt_source")
                with c_flt_q:
                    search_kw = st.text_input("タイトル検索:", placeholder="キーワードで絞り込み...", key="llm_search_kw")

                duckdb_path = paths.get("PATH_DUCKDB", os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
                use_duckdb = DuckDBManager is not None and os.path.exists(duckdb_path)
                db_conn = None

                page_size = 50
                page_key = f"llm_judg_page_{filter_status}_{filter_source}_{search_kw}"
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1

                cur_page = st.session_state[page_key]

                if use_duckdb:
                    try:
                        db_conn = DuckDBManager(db_path=duckdb_path)
                        # LLM判定がDB未反映なら同期
                        eval_check = db_conn.conn.execute("SELECT count(*) FROM metadata_records WHERE llm_evaluated = true;").fetchone()[0]
                        if eval_check == 0 and os.path.exists(llm_judgments_path):
                            db_conn.sync_llm_judgments(llm_judgments_path)

                        total_source_count = db_conn.get_record_count()
                        total_count, page_records = db_conn.query_records(
                            filter_status=filter_status,
                            filter_source=filter_source if filter_source != "すべて" else None,
                            search_query=search_kw,
                            page=cur_page,
                            page_size=page_size
                        )
                    except Exception as e:
                        if db_conn:
                            try:
                                db_conn.close()
                            except Exception:
                                pass
                        db_conn = None
                        use_duckdb = False

                if not use_duckdb:
                    # フォールバック: メモリ消費を最小化するストリーミングページネーション
                    total_source_count = 0
                    total_count = 0
                    start_idx = (cur_page - 1) * page_size
                    end_idx = start_idx + page_size
                    page_records = []

                    with open(llm_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if not line.strip():
                                continue
                            total_source_count += 1
                            try:
                                item = json.loads(line)
                            except Exception:
                                continue

                            tgt = item.get("is_target")
                            reason = str(item.get("reason", ""))
                            title = str(item.get("title", ""))

                            if filter_status == "適合 (true)のみ" and tgt is not True:
                                continue
                            if filter_status == "非適合 (false)のみ" and tgt is not False:
                                continue
                            if filter_status == "判定不能 (null)のみ" and tgt is not None:
                                continue

                            if filter_source == "Web情報補強 LLM判定" and "[ルール合格]" in reason:
                                continue
                            if filter_source == "ルール適合パス (LLMバイパス)" and "[ルール合格]" not in reason:
                                continue

                            if search_kw and search_kw.lower() not in title.lower():
                                continue

                            if start_idx <= total_count < end_idx:
                                page_records.append({
                                    "title": item.get("title", "無題"),
                                    "llm_target": tgt,
                                    "llm_reason": reason,
                                    "external_info": item.get("external_info", "")
                                })
                            total_count += 1

                total_pages = max(1, (total_count + page_size - 1) // page_size)
                if cur_page > total_pages:
                    st.session_state[page_key] = total_pages
                    cur_page = total_pages

                c_info, c_prev, c_pg_num, c_next = st.columns([2, 1, 1, 1])
                with c_info:
                    st.markdown(f"**該当件数: {total_count:,} 件** (全 {total_source_count:,} 件中)")
                with c_prev:
                    if st.button("前へ", disabled=(cur_page <= 1), use_container_width=True, key=f"btn_prev_{page_key}"):
                        st.session_state[page_key] = max(1, cur_page - 1)
                        if db_conn:
                            db_conn.close()
                        st.rerun()
                with c_pg_num:
                    new_page = st.number_input(
                        "ページ選択:",
                        min_value=1,
                        max_value=total_pages,
                        value=cur_page,
                        step=1,
                        key=f"num_{page_key}"
                    )
                    if new_page != cur_page:
                        st.session_state[page_key] = new_page
                        if db_conn:
                            db_conn.close()
                        st.rerun()
                with c_next:
                    if st.button("次へ", disabled=(cur_page >= total_pages), use_container_width=True, key=f"btn_next_{page_key}"):
                        st.session_state[page_key] = min(total_pages, cur_page + 1)
                        if db_conn:
                            db_conn.close()
                        st.rerun()

                # オンデマンド CSV ダウンロード (巨大DataFrame保持を回避)
                def generate_filtered_csv_bytes():
                    import io
                    import csv
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=["id", "title", "is_target", "reason", "external_info"])
                    writer.writeheader()
                    if use_duckdb and db_conn:
                        _, all_export_rows = db_conn.query_records(
                            filter_status=filter_status,
                            filter_source=filter_source if filter_source != "すべて" else None,
                            search_query=search_kw,
                            page=1,
                            page_size=1000000
                        )
                        for r in all_export_rows:
                            writer.writerow({
                                "id": r.get("id", ""),
                                "title": r.get("title", ""),
                                "is_target": r.get("llm_target"),
                                "reason": r.get("llm_reason", ""),
                                "external_info": r.get("external_info", "")
                            })
                    else:
                        with open(llm_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                try:
                                    item = json.loads(line)
                                except Exception:
                                    continue
                                tgt = item.get("is_target")
                                reason = str(item.get("reason", ""))
                                title = str(item.get("title", ""))
                                if filter_status == "適合 (true)のみ" and tgt is not True:
                                    continue
                                if filter_status == "非適合 (false)のみ" and tgt is not False:
                                    continue
                                if filter_status == "判定不能 (null)のみ" and tgt is not None:
                                    continue
                                if filter_source == "Web情報補強 LLM判定" and "[ルール合格]" in reason:
                                    continue
                                if filter_source == "ルール適合パス (LLMバイパス)" and "[ルール合格]" not in reason:
                                    continue
                                if search_kw and search_kw.lower() not in title.lower():
                                    continue
                                writer.writerow({
                                    "id": item.get("id", ""),
                                    "title": title,
                                    "is_target": tgt,
                                    "reason": reason,
                                    "external_info": item.get("external_info", "")
                                    })
                    return output.getvalue().encode('utf-8-sig')

                st.download_button(
                    label="抽出判定ログの CSV 出力",
                    data=generate_filtered_csv_bytes(),
                    file_name="llm_judgments_extracted.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                # 50件のレコード描画
                for item in page_records:
                    tgt = item.get("llm_target")
                    if tgt is True:
                        badge_html = "<span class='status-badge status-badge-pass'>適合</span>"
                    elif tgt is False:
                        badge_html = "<span class='status-badge status-badge-reject'>非適合</span>"
                    else:
                        badge_html = "<span class='status-badge status-badge-neutral'>判定不能</span>"

                    with st.container(border=True):
                        c_hdr1, c_hdr2 = st.columns([8.2, 1.8])
                        with c_hdr1:
                            st.markdown(f"**{item.get('title', '無題')}**")
                        with c_hdr2:
                            st.markdown(badge_html, unsafe_allow_html=True)

                        reason_text = item.get("llm_reason", "理由記述なし")
                        st.info(f"LLM判定理由: {reason_text}")

                        ext_info = item.get("external_info", "")
                        if ext_info and ext_info != "補足情報なし":
                            st.markdown("参照外部Web情報スニペット:")
                            st.code(ext_info, language="text")
                        elif "[ルール合格]" in str(reason_text):
                            st.caption("※事前ルール適合のためWeb検索およびLLM呼び出しをスキップしました。")

                if db_conn:
                    db_conn.close()
            else:
                st.info("LLM判定ログがまだ生成されていません。")

    # 最下部ナビゲーション
    render_step_navigation(
        prev_choice="Step 2-C: タイトル語彙・文字列パターン分析・除外",
        next_choice="Step 4: 専門家による最終査読・手動オーバーライド"
    )
