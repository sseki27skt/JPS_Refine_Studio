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
from modules.rule_filter import split_dataset_by_rules
from modules.llm_classifier import run_llm_semantic_classification, run_stage2_llm_classification

def render_step2c_view(paths: dict):
    """Step 3 画面の描画"""
    st.title("Step 3: LLMセマンティック適合判定 (判定保留群の分類)")
    st.caption("事前ルールフィルタで確定しなかった判定保留（グレーゾーン）データを抽出し、LLMによるテキスト解釈と根拠理由生成に基づくセマンティック適合判定を行います。")

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

    # 既存の分割結果が存在するかチェック (不要な毎フレーム再計算を防止)
    has_split_files = os.path.exists(target_for_llm_path) and os.path.exists(confirmed_ok_path)

    def do_split():
        with st.spinner("ルールに基づいてデータを仕分け中 (OK合格 / NG除外 / グレーゾーン)..."):
            ok_c, ng_c, grey_c = split_dataset_by_rules(
                input_jsonl_path=raw_input_path,
                about_rules_path=about_rules_path,
                ngram_rules_path=ngram_rules_path,
                output_target_for_llm_jsonl=target_for_llm_path,
                output_confirmed_ok_jsonl=confirmed_ok_path,
                output_discarded_csv=discarded_rules_path
            )
            return ok_c, ng_c, grey_c

    # ファイル未生成時のみ初回実行
    if not has_split_files:
        ok_rules_cnt, ng_rules_cnt, grey_cnt = do_split()
    else:
        ok_rules_cnt = count_lines(confirmed_ok_path)
        ng_rules_cnt = count_lines(discarded_rules_path)
        if ng_rules_cnt > 0:
            ng_rules_cnt -= 1 # CSVヘッダー分
        grey_cnt = count_lines(target_for_llm_path)

    # ステータス表示
    st.markdown("### 事前ルールフィルタによる仕分け状況")
    c_flt1, c_flt2, c_flt3, c_flt_act = st.columns([2.5, 2.5, 2.5, 2.5])
    with c_flt1:
        st.metric("ルール適合 (LLMバイパス)", f"{ok_rules_cnt:,} 件", help="About/タイトルルールでOK判定されたためLLM判定をスキップ")
    with c_flt2:
        st.metric("ルール除外 (事前除外)", f"{ng_rules_cnt:,} 件", help="About/タイトルルールでNG判定されたため事前除外")
    with c_flt3:
        st.metric("LLM判定対象 (判定保留群)", f"{grey_cnt:,} 件", help="判定保留のデータ。これらのみがLLMへ投入されます。")
    with c_flt_act:
        st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 ルール仕分けの再実行", help="Step 2の最新ルールを反映して仕分けファイルを再作成します", use_container_width=True):
            ok_rules_cnt, ng_rules_cnt, grey_cnt = do_split()
            st.success(f"最新ルールで再仕分け完了 (保留: {grey_cnt:,} 件)")
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
        for p in [llm_judgments_path, f"{data_dir}/tmp_llm_grey_judgments.jsonl"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        st.cache_data.clear()
        st.session_state["stop_llm_flag"] = False
        st.success("LLM判定結果ログを初期化しました。")
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
                status_text.markdown(f"進捗: **{current}/{total}** | {badge} **{title[:35]}** ➔ *{reason}*")

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
                    st2_status_text.markdown(f"Stage 2 進捗: **{current}/{total}** 件 | {badge} **{title[:35]}** ➔ *{reason}*")

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
            all_judgments = []
            with open(llm_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.strip():
                        try:
                            all_judgments.append(json.loads(line))
                        except Exception:
                            pass

            if all_judgments:
                c_flt_t, c_flt_s, c_flt_q = st.columns(3)
                with c_flt_t:
                    filter_status = st.selectbox("判定結果で絞り込み:", ["すべて", "適合 (true)のみ", "非適合 (false)のみ", "判定不能 (null)のみ"])
                with c_flt_s:
                    filter_source = st.selectbox("判定ソースで絞り込み:", ["すべて", "Web情報補強 LLM判定", "ルール適合パス (LLMバイパス)"])
                with c_flt_q:
                    search_kw = st.text_input("タイトル検索:", placeholder="キーワードで絞り込み...")

                filtered_judgments = []
                for item in all_judgments:
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

                    filtered_judgments.append(item)

                st.caption(f"該当件数: **{len(filtered_judgments)}** / 全 {len(all_judgments)} 件")

                c_dl, c_pg_size, c_pg_num = st.columns([2, 1, 1])
                with c_dl:
                    df_full_export = pd.DataFrame(filtered_judgments)
                    csv_data = df_full_export.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="抽出判定ログの CSV 出力",
                        data=csv_data,
                        file_name="llm_judgments_extracted.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with c_pg_size:
                    page_size = st.selectbox("1ページの表示件数:", [10, 20, 50, 100], index=0)
                with c_pg_num:
                    total_pages = max(1, (len(filtered_judgments) + page_size - 1) // page_size)
                    page_num = st.number_input("ページ選択:", min_value=1, max_value=total_pages, value=1, step=1)

                start_idx = (page_num - 1) * page_size
                page_items = filtered_judgments[start_idx : start_idx + page_size]

                for item in page_items:
                    tgt = item.get("is_target")
                    if tgt is True:
                        badge_label = "適合 (true)"
                    elif tgt is False:
                        badge_label = "非適合 (false)"
                    else:
                        badge_label = "判定不能 (null)"

                    with st.container(border=True):
                        c_hdr1, c_hdr2 = st.columns([3, 1])
                        with c_hdr1:
                            st.markdown(f"### {item.get('title', '無題')}")
                        with c_hdr2:
                            st.markdown(f"### `{badge_label}`")

                        reason_text = item.get("reason", "理由記述なし")
                        st.info(f"LLM判定理由: {reason_text}")

                        ext_info = item.get("external_info", "")
                        if ext_info and ext_info != "補足情報なし":
                            st.markdown("参照外部Web情報スニペット:")
                            st.code(ext_info, language="text")
                        elif "[ルール合格]" in reason_text:
                            st.caption("※事前ルール適合のためWeb検索およびLLM呼び出しをスキップしました。")
