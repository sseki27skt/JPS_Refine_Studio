# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 1: LLMクエリ拡張 ＆ Japan Searchメタデータ一括取得ビュー
"""
import os
import re
import json
import time
import streamlit as st
from modules.llm_query_expander import (
    expand_query_with_llm, 
    generate_sparql_queries, 
    optimize_keywords_for_regex, 
    optimize_regex_str,
    NDC_MASTER,
    TYPE_MASTER,
    ndc_codes_to_labels,
    ndc_labels_to_codes
)
import pandas as pd
from modules.sparql_collector import (
    fetch_uris_with_query_func, 
    build_metadata_for_uris,
    check_metadata_completeness,
    verify_and_repair_metadata
)

def _on_rebuild_regex():
    kw_input_text = st.session_state.get("input_kw_manual", "")
    selected_ndc_labels = st.session_state.get("input_ndc_multiselect", [])
    selected_ex_ndc_labels = st.session_state.get("input_exclude_ndc_multiselect", [])
    ex_ndc_codes_input = st.session_state.get("input_exclude_ndc_codes_manual", "")
    domain_def_input = st.session_state.get("input_domain_def_manual", "")

    parsed_kws = [w.strip() for w in re.split(r"[\n,・/／]+", kw_input_text) if w.strip()]
    parsed_ndc = ndc_labels_to_codes(selected_ndc_labels)
    
    parsed_ex_ndc_from_select = ndc_labels_to_codes(selected_ex_ndc_labels)
    parsed_ex_ndc_from_text = [c.strip() for c in re.split(r"[\n,・/／]+", ex_ndc_codes_input) if c.strip()]
    combined_ex_ndc = sorted(list(set(parsed_ex_ndc_from_select + parsed_ex_ndc_from_text)))
    
    st.session_state["input_ndc_codes_manual"] = ", ".join(parsed_ndc)
    st.session_state["input_exclude_ndc_codes_manual"] = ", ".join(combined_ex_ndc)

    opt_kws = optimize_keywords_for_regex(parsed_kws)
    rebuilt_regex = "|".join(opt_kws)

    st.session_state["input_title_regex_manual"] = rebuilt_regex
    st.session_state["input_desc_regex_manual"] = rebuilt_regex

    exp = st.session_state.get("expansion_res", {})
    exp["keywords"] = parsed_kws
    exp["ndc_codes"] = parsed_ndc
    exp["exclude_ndc_codes"] = combined_ex_ndc
    exp["title_regex"] = rebuilt_regex
    exp["desc_regex"] = rebuilt_regex
    exp["domain_definition"] = domain_def_input.strip()
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = "キーワード一覧に基づく正規表現パターンの再構築および最適化が完了しました。"


def _on_populate_exclude_ndc_from_complement():
    selected_ndc_labels = st.session_state.get("input_ndc_multiselect", [])
    ndc_codes_input = st.session_state.get("input_ndc_codes_manual", "")
    
    parsed_ndc_from_select = ndc_labels_to_codes(selected_ndc_labels)
    parsed_ndc_from_text = [c.strip() for c in re.split(r"[\n,・/／]+", ndc_codes_input) if c.strip()]
    included_codes = set(parsed_ndc_from_select + parsed_ndc_from_text)
    
    # 包含コードと競合・衝突する二次区分（00-99）を特定して保護
    # 例: 包含コードに "76" や "768" がある場合、除外リストに "76" を入れると前方一致で "768" も消えてしまうため除外不可とする
    protected_2digit = set()
    for code in included_codes:
        c = code.replace(".", "").strip()
        if len(c) == 1:
            for i in range(10):
                protected_2digit.add(f"{c}{i}")
        elif len(c) >= 2:
            protected_2digit.add(c[:2])
    
    # 全NDC二次区分（00-99）から包含関連コードを除いた補集合を計算
    all_2digit = sorted(list(NDC_MASTER.keys()))
    complement_codes = [c for c in all_2digit if c not in protected_2digit]
    
    st.session_state["input_exclude_ndc_multiselect"] = ndc_codes_to_labels(complement_codes)
    st.session_state["input_exclude_ndc_codes_manual"] = ", ".join(complement_codes)
    
    exp = st.session_state.get("expansion_res", {})
    exp["exclude_ndc_codes"] = complement_codes
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = f"OK(包含)リスト以外の全NDC二次区分（{len(complement_codes)}件）を除外(Blacklist)リストに一括設定しました。"


def _on_clear_exclude_ndc():
    st.session_state["input_exclude_ndc_multiselect"] = []
    st.session_state["input_exclude_ndc_codes_manual"] = ""
    exp = st.session_state.get("expansion_res", {})
    exp["exclude_ndc_codes"] = []
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = "除外NDCリストをクリアしました。"


def _on_apply_manual_params():
    kw_input_text = st.session_state.get("input_kw_manual", "")
    selected_ndc_labels = st.session_state.get("input_ndc_multiselect", [])
    ndc_codes_input = st.session_state.get("input_ndc_codes_manual", "")
    selected_ex_ndc_labels = st.session_state.get("input_exclude_ndc_multiselect", [])
    ex_ndc_codes_input = st.session_state.get("input_exclude_ndc_codes_manual", "")
    title_regex_input = st.session_state.get("input_title_regex_manual", "")
    desc_regex_input = st.session_state.get("input_desc_regex_manual", "")
    domain_def_input = st.session_state.get("input_domain_def_manual", "")
    selected_rdf_types = st.session_state.get("input_rdf_types_multiselect", [])
    selected_whitelist_rdf_types = st.session_state.get("input_rdf_types_whitelist_multiselect", [])

    parsed_kws = [w.strip() for w in re.split(r"[\n,・/／]+", kw_input_text) if w.strip()]
    
    parsed_ndc_from_select = ndc_labels_to_codes(selected_ndc_labels)
    parsed_ndc_from_text = [c.strip() for c in re.split(r"[\n,・/／]+", ndc_codes_input) if c.strip()]
    combined_ndc = sorted(list(set(parsed_ndc_from_select + parsed_ndc_from_text)))

    parsed_ex_ndc_from_select = ndc_labels_to_codes(selected_ex_ndc_labels)
    parsed_ex_ndc_from_text = [c.strip() for c in re.split(r"[\n,・/／]+", ex_ndc_codes_input) if c.strip()]
    combined_ex_ndc = sorted(list(set(parsed_ex_ndc_from_select + parsed_ex_ndc_from_text)))

    auto_rebuilt_regex = "|".join(optimize_keywords_for_regex(parsed_kws))

    final_title_regex = optimize_regex_str(title_regex_input.strip()) if title_regex_input.strip() else auto_rebuilt_regex
    final_desc_regex = optimize_regex_str(desc_regex_input.strip()) if desc_regex_input.strip() else auto_rebuilt_regex

    st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(combined_ndc)
    st.session_state["input_ndc_codes_manual"] = ", ".join(combined_ndc)
    st.session_state["input_exclude_ndc_multiselect"] = ndc_codes_to_labels(combined_ex_ndc)
    st.session_state["input_exclude_ndc_codes_manual"] = ", ".join(combined_ex_ndc)
    st.session_state["input_title_regex_manual"] = final_title_regex
    st.session_state["input_desc_regex_manual"] = final_desc_regex

    exp = st.session_state.get("expansion_res", {})
    exp["keywords"] = parsed_kws
    exp["ndc_codes"] = combined_ndc
    exp["exclude_ndc_codes"] = combined_ex_ndc
    exp["title_regex"] = final_title_regex
    exp["desc_regex"] = final_desc_regex
    exp["domain_definition"] = domain_def_input.strip()
    exp["blacklist_rdf_types"] = [TYPE_MASTER[k] for k in selected_rdf_types if k in TYPE_MASTER]
    exp["whitelist_rdf_types"] = [TYPE_MASTER[k] for k in selected_whitelist_rdf_types if k in TYPE_MASTER]
    st.session_state["expansion_res"] = exp
    st.session_state["msg_success"] = "設定パラメータの保存・適用が完了しました。"


def render_step1_view(paths: dict):
    """Step 1 画面の描画"""
    st.title("Step 1: LLMクエリ拡張およびJapan Searchメタデータ取得")
    st.caption("対象テーマに基づき、LLMを用いて異体字・旧字体・関連用語を拡張し、再現率（Recall）を最大化する検索クエリを生成してJapan Searchよりデータを一括取得します。")

    # --- 1. テーマ入力 ---
    theme_input = st.text_input(
        "対象テーマ・関心領域の指定:", 
        value="日本の古典籍における楽譜資料", 
        help="例: 日本の古典籍における楽譜資料、江戸時代の古地図、能楽演目文献 など"
    )

    # session_state の初期化（初回ロード時）
    if "expansion_res" not in st.session_state:
        words = [w.strip() for w in re.split(r"[\s,・/／におけるについて等の文献資料]+", theme_input) if len(w.strip()) >= 2]
        init_kws = words if words else [theme_input]
        opt_kws = optimize_keywords_for_regex(init_kws)
        init_regex = "|".join(opt_kws)
        
        st.session_state["expansion_res"] = {
            "theme": theme_input,
            "domain_definition": f"「{theme_input}」に関連する文化資源・文献・資料",
            "keywords": init_kws,
            "ndc_codes": [],
            "title_regex": init_regex,
            "desc_regex": init_regex,
            "blacklist_rdf_types": [],
            "whitelist_rdf_types": [],
            "is_fallback": False,
            "fallback_reason": None
        }

    # --- 2. LLMによる自動拡張セクション ---
    st.markdown("---")
    st.subheader("1. LLMによる検索キーワード・クエリ条件の自動拡張")
    st.caption("大型言語モデル（LLM）を活用し、対象テーマに関連する異体字・旧字体・ドメイン専門用語・NDC分類コードを体系的に抽出します。")

    provider_choice = st.selectbox(
        "使用するLLMプロバイダーを選択:",
        ["Google Gemini API (推奨・高速)", "LM Studio (ローカル)", "OpenAI API", "その他カスタムAPI"],
        index=0
    )

    provider_code = "local"
    api_key_input = ""
    api_base_input = "http://localhost:1234/v1"
    model_input = "gemini-3.6-flash"

    if "Google Gemini" in provider_choice:
        provider_code = "gemini"
        env_gemini_key = os.environ.get("GEMINI_API_KEY", "")
        api_key_input = st.text_input("Google Gemini API Key:", value=env_gemini_key, type="password", help="APIキーを入力してください")
        model_input = st.selectbox(
            "モデル選択:", 
            [
                "gemini-3.6-flash", 
                "gemini-3.5-flash", 
                "gemini-3.5-flash-lite", 
                "gemini-3.1-flash-lite", 
                "gemini-1.5-flash", 
                "gemini-1.5-pro"
            ], 
            index=0
        )
    elif "LM Studio" in provider_choice:
        provider_code = "local"
        api_base_input = st.text_input("LM Studio API エンドポイント:", value="http://localhost:1234/v1")
        model_input = st.text_input("モデル名:", value="local-model")
    elif "OpenAI" in provider_choice:
        provider_code = "openai"
        env_openai_key = os.environ.get("OPENAI_API_KEY", "")
        api_key_input = st.text_input("OpenAI API Key:", value=env_openai_key, type="password")
        api_base_input = "https://api.openai.com/v1"
        model_input = st.selectbox("モデル選択:", ["gpt-4o-mini", "gpt-4o"], index=0)

    st.session_state["llm_config"] = {
        "provider": provider_code,
        "api_base": api_base_input,
        "api_key": api_key_input,
        "model": model_input
    }

    if st.button("LLMによる検索キーワード・クエリ条件の自動拡張を実行", type="primary", use_container_width=True):
        with st.spinner("LLMによるドメイン分析および検索キーワードの拡張処理を実行中..."):
            expansion_res = expand_query_with_llm(
                theme_prompt=theme_input,
                provider=provider_code,
                api_base=api_base_input,
                api_key=api_key_input,
                model=model_input
            )
            st.session_state["expansion_res"] = expansion_res
            
            ndc_codes_res = expansion_res.get("ndc_codes", [])
            exclude_ndc_res = expansion_res.get("exclude_ndc_codes", [])
            st.session_state["input_kw_manual"] = "\n".join(expansion_res.get("keywords", [])) if isinstance(expansion_res.get("keywords"), list) else str(expansion_res.get("keywords", ""))
            st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(ndc_codes_res)
            st.session_state["input_ndc_codes_manual"] = ", ".join(ndc_codes_res) if isinstance(ndc_codes_res, list) else str(ndc_codes_res)
            st.session_state["input_exclude_ndc_multiselect"] = ndc_codes_to_labels(exclude_ndc_res)
            st.session_state["input_exclude_ndc_codes_manual"] = ", ".join(exclude_ndc_res) if isinstance(exclude_ndc_res, list) else str(exclude_ndc_res)
            st.session_state["input_title_regex_manual"] = expansion_res.get("title_regex", "")
            st.session_state["input_desc_regex_manual"] = expansion_res.get("desc_regex", "")
            st.session_state["input_domain_def_manual"] = expansion_res.get("domain_definition", "")

            st.success("LLMによる検索キーワードおよび検索条件の自動拡張処理が完了しました。")
            st.rerun()

    exp = st.session_state["expansion_res"]

    with st.expander("高度な設定: 検索パラメータの入出力 (JSON)", expanded=False):
        st.caption("以前成功した検索パラメータ(JSON)をコピペして使い回すことができます。")
        current_json = json.dumps(exp, ensure_ascii=False, indent=2)
        st.code(current_json, language="json")
        
        col_j1, col_j2 = st.columns([3, 1])
        with col_j1:
            pasted_json = st.text_area("適用したいJSONパラメータを貼り付け:", height=100)
        with col_j2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("JSONを適用", use_container_width=True):
                if pasted_json.strip():
                    try:
                        loaded_exp = json.loads(pasted_json)
                        st.session_state["expansion_res"] = loaded_exp
                        # Force refresh widget states
                        for k in ["input_kw_manual", "input_ndc_multiselect", "input_ndc_codes_manual", "input_exclude_ndc_multiselect", "input_exclude_ndc_codes_manual", "input_title_regex_manual", "input_desc_regex_manual", "input_domain_def_manual", "input_rdf_types_multiselect", "input_rdf_types_whitelist_multiselect"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.success("JSONからパラメータを読み込みました！画面が更新されます。")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"JSONのパースに失敗しました: {e}")
                else:
                    st.warning("JSONを入力してください。")


    # Widget キーの初期値が未設定の場合のみ初期値をセット
    if "input_kw_manual" not in st.session_state:
        cur_kws = exp.get("keywords", [])
        st.session_state["input_kw_manual"] = "\n".join(cur_kws) if isinstance(cur_kws, list) else str(cur_kws)
    if "input_ndc_multiselect" not in st.session_state:
        cur_ndc = exp.get("ndc_codes", [])
        st.session_state["input_ndc_multiselect"] = ndc_codes_to_labels(cur_ndc)
    if "input_ndc_codes_manual" not in st.session_state:
        cur_ndc = exp.get("ndc_codes", [])
        st.session_state["input_ndc_codes_manual"] = ", ".join(cur_ndc) if isinstance(cur_ndc, list) else str(cur_ndc)
    if "input_exclude_ndc_multiselect" not in st.session_state:
        cur_ex_ndc = exp.get("exclude_ndc_codes", [])
        st.session_state["input_exclude_ndc_multiselect"] = ndc_codes_to_labels(cur_ex_ndc)
    if "input_exclude_ndc_codes_manual" not in st.session_state:
        cur_ex_ndc = exp.get("exclude_ndc_codes", [])
        st.session_state["input_exclude_ndc_codes_manual"] = ", ".join(cur_ex_ndc) if isinstance(cur_ex_ndc, list) else str(cur_ex_ndc)
    if "input_title_regex_manual" not in st.session_state:
        st.session_state["input_title_regex_manual"] = exp.get("title_regex", "")
    if "input_desc_regex_manual" not in st.session_state:
        st.session_state["input_desc_regex_manual"] = exp.get("desc_regex", "")
    if "input_domain_def_manual" not in st.session_state:
        st.session_state["input_domain_def_manual"] = exp.get("domain_definition", f"「{theme_input}」に関連する資料")
    if "input_rdf_types_multiselect" not in st.session_state:
        cur_types = exp.get("blacklist_rdf_types", exp.get("rdf_types", []))
        inv_type_map = {v: k for k, v in TYPE_MASTER.items()}
        st.session_state["input_rdf_types_multiselect"] = [inv_type_map[uri] for uri in cur_types if uri in inv_type_map]
    if "input_rdf_types_whitelist_multiselect" not in st.session_state:
        cur_w_types = exp.get("whitelist_rdf_types", [])
        inv_type_map = {v: k for k, v in TYPE_MASTER.items()}
        st.session_state["input_rdf_types_whitelist_multiselect"] = [inv_type_map[uri] for uri in cur_w_types if uri in inv_type_map]

    # フォールバック通知表示
    if exp.get("is_fallback"):
        st.warning(
            "⚠️ LLMへの接続ができなかったため、フォールバック（ルールベース生成）が適用されました。\n"
            f"理由: `{exp.get('fallback_reason')}`"
        )

    # --- 3. 収集用検索キーワード・パラメータの手動調整セクション ---
    st.markdown("---")
    st.subheader("2. 検索キーワードおよび抽出条件の手動検証・編集")
    st.caption("LLMによって提案されたパラメータを検証し、キーワードの追加・除外、NDC分類の選択、正規表現の修正を自由に行えます。")

    c_edit1, c_edit2 = st.columns(2)
    with c_edit1:
        kw_input_text = st.text_area(
            "検索キーワード一覧 (改行またはカンマ区切り):",
            height=200,
            key="input_kw_manual"
        )

        title_regex_input = st.text_input(
            "タイトル・主題用 正規表現 (REGEX) パターン (`|` 区切り):",
            key="input_title_regex_manual"
        )
        desc_regex_input = st.text_input(
            "内容記述 (schema:description) 用 正規表現 (REGEX) パターン (`|` 区切り):",
            key="input_desc_regex_manual"
        )

    with c_edit2:
        all_types = list(TYPE_MASTER.keys())

        wl_selected = st.multiselect(
            "問答無用で全件取得する rdf:type (ホワイトリスト):",
            options=all_types,
            help="指定したカテゴリを持つ資料をキーワードの有無に関わらず全件取得します。※「図書」など巨大なカテゴリの指定は避けてください。",
            key="input_rdf_types_whitelist_multiselect"
        )

        bl_selected = st.multiselect(
            "除外する rdf:type (資料種別):",
            options=all_types,
            help="指定したカテゴリを持つ資料を検索対象から除外します。明らかなノイズ（例：動物標本など）を弾くことで、網羅性を保ちながら検索速度を向上させます。",
            key="input_rdf_types_multiselect"
        )
        
        # 矛盾チェック（ホワイトリストとブラックリストの重複）
        overlap = set(wl_selected).intersection(set(bl_selected))
        if overlap:
            st.error(f"⚠️ **指定の矛盾**: 以下のタイプがホワイトリストとブラックリストの両方に指定されています。正常に処理できないため、どちらかから削除してください。\n\n **重複項目**: {', '.join(overlap)}")

        st.markdown("##### 📚 NDC (日本十進分類法) 分類コード指定")
        
        # 包含NDC
        st.multiselect(
            "包含 (取得対象) NDC 二次区分選択リスト:",
            options=list(NDC_MASTER.values()),
            help="指定したNDCを持つ資料を網羅検索クエリで追加収集します",
            key="input_ndc_multiselect"
        )
        ndc_codes_input = st.text_input(
            "包含 NDC 分類コード (手動入力・連動):",
            help="例: 76, 77, 18 (マルチセレクトと自動連動します)",
            key="input_ndc_codes_manual"
        )

        # 除外NDC (Blacklist)
        st.multiselect(
            "🚫 除外 (Blacklist / ノイズ) NDC 二次区分選択リスト:",
            options=list(NDC_MASTER.values()),
            help="指定したNDCを持つ資料は、タイトル等にキーワードが含まれていても SPARQL 検索時点でブロック・除外します",
            key="input_exclude_ndc_multiselect"
        )
        ex_ndc_codes_input = st.text_input(
            "除外 NDC 分類コード (手動入力・連動):",
            help="例: 375, 49, 59, 288, 51 (細分類コードも入力可能です)",
            key="input_exclude_ndc_codes_manual"
        )
        
        c_ndc_btn1, c_ndc_btn2 = st.columns(2)
        with c_ndc_btn1:
            st.button(
                "➕ OKリスト以外を一括除外に追加",
                on_click=_on_populate_exclude_ndc_from_complement,
                help="包含(OK)リストに含まれていない全てのNDC二次区分（00〜99）を除外(Blacklist)リストに一括設定します",
                use_container_width=True
            )
        with c_ndc_btn2:
            st.button(
                "🗑️ 除外リストをクリア",
                on_click=_on_clear_exclude_ndc,
                help="除外NDCリストを空にします",
                use_container_width=True
            )

    domain_def_input = st.text_area(
        "ドメイン定義文 (Step 2-C セマンティック適合判定の評価基準):",
        height=70,
        key="input_domain_def_manual"
    )

    c_sync1, c_sync2 = st.columns([2, 1])
    with c_sync1:
        st.button(
            "キーワード一覧からの正規表現パターン自動再構築・最適化", 
            on_click=_on_rebuild_regex, 
            use_container_width=True
        )

    with c_sync2:
        st.button(
            "設定パラメータの保存・適用", 
            type="primary", 
            on_click=_on_apply_manual_params, 
            use_container_width=True
        )

    if "msg_success" in st.session_state and st.session_state["msg_success"]:
        st.success(st.session_state.pop("msg_success"))

    # --- 4. SPARQLクエリ表示 ＆ 実行セクション ---
    st.markdown("---")
    exp = st.session_state["expansion_res"]

    with st.expander("現在適用中の検索パラメータ (JSON)", expanded=False):
        st.json(exp)

    queries = generate_sparql_queries(exp)
    st.subheader(f"3. 実行対象SPARQLクエリパターン ({len(queries)} パターン)")
    st.caption("定義されたキーワード、NDC分類コード、正規表現パターンに基づき生成されたSPARQLクエリ:")

    c_lim1, c_lim2 = st.columns([1, 1])
    with c_lim1:
        is_unlimited = st.checkbox(
            "🌐 全件網羅収集モード (上限なし・尽きるまで全件取得)", 
            value=True, 
            help="各クエリパターンに合致するすべての文化資源メタデータを、件数制限なく最後まで収集します（推奨・Recall 100%）。"
        )
    with c_lim2:
        if is_unlimited:
            batch_size_val = st.number_input("単回リクエスト件数 (LIMIT):", min_value=100, max_value=1000, value=500, step=100, help="1回のリクエストで取得する件数。通常500で最速です。")
            limit_val = batch_size_val
        else:
            limit_val = st.number_input("1パターンあたりの取得上限件数:", min_value=50, max_value=10000, value=200, step=50)

    if st.button("Japan Searchからの関連メタデータ一括取得および構造化実行", type="primary", use_container_width=True):
        status_box = st.empty()
        progress_bar = st.progress(0)
        
        all_collected_uris = set()
        failed_queries = []

        # Phase 1: 一斉クエリ取得
        total_steps = len(queries)
        for idx, (name, func) in enumerate(queries):
            def on_phase1_progress(p_name, current_pattern_count):
                status_box.markdown(
                    f"全 {len(queries)} パターン中 **{idx+1} パターン目**: `[{name}]` を収集中...  \n"
                    f"・このパターンの取得数: **{current_pattern_count:,} 件**  \n"
                    f"・現在までの全体累計 (重複除外前概算): **{len(all_collected_uris) + current_pattern_count:,} 件**"
                )

            on_phase1_progress(name, 0)
            uris, success = fetch_uris_with_query_func(
                func, 
                pattern_name=name, 
                limit=limit_val, 
                unlimited=is_unlimited, 
                progress_callback=on_phase1_progress, 
                timeout_sec=45
            )
            all_collected_uris.update(uris)
            if not success:
                failed_queries.append((name, func))
            progress_bar.progress((idx + 1) / total_steps)

        # Phase 2: 応答遅延パターンの自動再取得フェーズ
        if failed_queries:
            status_box.warning(f"初回応答遅延が発生した {len(failed_queries)} 件のクエリパターンに対して、3秒待機後に自動再読み込みを実行します...")
            time.sleep(3)
            for idx, (name, func) in enumerate(failed_queries):
                def on_phase2_progress(p_name, current_pattern_count):
                    status_box.markdown(
                        f"自動再取得フェーズ [{idx+1}/{len(failed_queries)}]: `[{name}]` を再読み込み中...  \n"
                        f"・現在までの全体累計: **{len(all_collected_uris) + current_pattern_count:,} 件**"
                    )

                on_phase2_progress(name, 0)
                uris, success = fetch_uris_with_query_func(
                    func, 
                    pattern_name=f"{name} (再試行)", 
                    limit=limit_val, 
                    unlimited=is_unlimited, 
                    progress_callback=on_phase2_progress, 
                    timeout_sec=60
                )
                all_collected_uris.update(uris)
                if success:
                    st.info(f"再取得成功: `[{name}]` から追加データを正常に取得しました。")

        st.success(f"リソースURIの収集完了: 重複のない **{len(all_collected_uris):,} 件** の対象URIを取得しました。")
        
        # 対象URI一覧を CSV に永続化
        unique_uri_list = sorted(list(all_collected_uris))
        df_target_uris = pd.DataFrame({"uri": unique_uri_list})
        df_target_uris.to_csv(paths['PATH_TARGET_URIS'], index=False, encoding='utf-8')
        st.caption(f"対象URI一覧を `{paths['PATH_TARGET_URIS']}` に保存しました。")
        
        def on_build_progress(done_count, total_count):
            status_box.markdown(f"詳細書誌メタデータ構築中: **{done_count:,} / {total_count:,} 件** 完了 ({done_count/total_count*100:.1f}%)")
            progress_bar.progress(done_count / total_count)

        with st.spinner(f"詳細書誌メタデータ（全 {len(unique_uri_list):,} 件）の深層グラフ構築処理を実行中..."):
            count = build_metadata_for_uris(
                unique_uri_list, 
                paths['PATH_RAW_METADATA'], 
                batch_size=10, 
                progress_callback=on_build_progress,
                auto_repair=True
            )
            st.success(f"メタデータ構築完了: 全 {count:,} 件の構造化データを `{paths['PATH_RAW_METADATA']}` に保存しました。")

    # --- 5. メタデータ完全性検証 ＆ 欠損自動修復セクション ---
    st.markdown("---")
    st.subheader("4. 取得済みメタデータの整合性・完全性検証 ＆ 欠損自動修復")
    st.caption("収集されたすべてのURIに対して、深層メタデータ（JSON）が欠落なく正常に取得できているかを照合・検証し、取得失敗（504・タイムアウト等）や未取得のデータがあれば自動で再取得してマージ・修復します。")

    raw_path = paths['PATH_RAW_METADATA']
    target_uris_path = paths['PATH_TARGET_URIS']

    # 対象URIリストの特定（CSVがあればCSVから、なければraw_metadataから抽出）
    target_uris_for_check = []
    if os.path.exists(target_uris_path):
        try:
            df_u = pd.read_csv(target_uris_path)
            if 'uri' in df_u.columns:
                target_uris_for_check = df_u['uri'].dropna().unique().tolist()
        except Exception:
            pass

    if not target_uris_for_check and os.path.exists(raw_path):
        try:
            with open(raw_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        u = item.get("@id", item.get("id", item.get("uri", "")))
                        if u:
                            target_uris_for_check.append(u)
            target_uris_for_check = sorted(list(set(target_uris_for_check)))
        except Exception:
            pass

    if target_uris_for_check:
        report = check_metadata_completeness(target_uris_for_check, raw_path)

        c_v1, c_v2, c_v3, c_v4 = st.columns(4)
        with c_v1:
            st.metric("総対象URI数", f"{report['total_target']:,} 件")
        with c_v2:
            st.metric("正常取得完了数", f"{report['valid_count']:,} 件", delta=f"{report['valid_count']/max(1,report['total_target']):.1%}")
        with c_v3:
            st.metric("取得失敗 (status:failed)", f"{report['failed_count']:,} 件", delta_color="inverse" if report['failed_count'] > 0 else "off")
        with c_v4:
            st.metric("未取得 (未処理)", f"{report['missing_count']:,} 件", delta_color="inverse" if report['missing_count'] > 0 else "off")

        if report['is_complete']:
            st.success(f"✅ 完全性チェック合格: 全 {report['total_target']:,} 件すべてのメタデータが正常に取得・格納されています。欠損はありません。")
        else:
            total_missing = len(report['need_retry_uris'])
            st.warning(f"⚠️ 合計 **{total_missing:,} 件** のメタデータに欠損または取得失敗が検知されました。以下のボタンより自動再取得（修復）を実行できます。")

            with st.expander("欠損・取得失敗URI一覧（先頭50件）", expanded=False):
                st.write(report['need_retry_uris'][:50])

            if st.button("🛠️ 欠損・失敗メタデータの自動再取得（自律リカバリー）を実行", type="primary", use_container_width=True):
                repair_status = st.empty()
                repair_progress = st.progress(0)

                def on_repair_progress(round_idx, done_cnt, total_cnt, recovered_cnt):
                    repair_status.markdown(
                        f"修復ラウンド **第 {round_idx} 回**: "
                        f"**{done_cnt:,} / {total_cnt:,} 件** 再取得試行中... "
                        f"(今回修復成功: **{recovered_cnt:,} 件**)"
                    )
                    repair_progress.progress(min(1.0, done_cnt / max(1, total_cnt)))

                with st.spinner("欠損メタデータのフォールバック再取得および修復マージを実行中..."):
                    final_rep = verify_and_repair_metadata(
                        target_uris_for_check, 
                        raw_path, 
                        max_repair_rounds=3, 
                        progress_callback=on_repair_progress
                    )

                if final_rep['is_complete']:
                    st.success(f"🎉 修復完了: 全 {final_rep['total_target']:,} 件のメタデータがすべて正常に取得されました！")
                else:
                    st.info(f"修復完了: 正常取得 {final_rep['valid_count']:,} 件 / 残り未修復 {len(final_rep['need_retry_uris']):,} 件")
                time.sleep(1)
                st.rerun()
    else:
        st.info("メタデータ取得実行後に、このセクションで全件の整合性チェックおよび欠損補完を実行できます。")

