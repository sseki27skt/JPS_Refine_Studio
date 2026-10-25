# -*- coding: utf-8 -*-
"""
ルールベースフィルタ (About/接尾辞) モジュール ＋ LLMキーワードサジェスト機能 (Gemini API / OpenAI / Local対応)
"""

import json
import os
import re
import urllib.parse
import requests
from .logger import logger
from collections import Counter

DEFAULT_LLM_URL = os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "local-model")


def extract_about_values(about_val) -> list:
    """
    schema:about の生表現（str, dict, list, またはそのネスト）から
    キーワード名 / URL解読名の一覧をリストとして抽出します。
    """
    if not about_val:
        return []
    
    raw_list = about_val if isinstance(about_val, list) else [about_val]
    keywords = []
    
    for item in raw_list:
        if not item:
            continue
        if isinstance(item, dict):
            val = item.get("rdfs:label") or item.get("schema:name") or item.get("@id") or ""
            if isinstance(val, list) and val:
                val = val[0]
            val_str = str(val).strip()
        else:
            val_str = str(item).strip()
            
        if not val_str:
            continue
            
        if val_str.startswith("http"):
            kw_name = urllib.parse.unquote(val_str.split("/")[-1])
            if kw_name:
                keywords.append(kw_name)
        else:
            keywords.append(val_str)
            
    return keywords


def extract_about_keywords_from_jsonl(input_jsonl_path: str) -> list:
    """
    raw_metadata.jsonl から schema:about のキーワードを抽出・カウント集計し、
    [(キーワード, 出現件数), ...] の降順リストとして返します。
    """
    if not os.path.exists(input_jsonl_path):
        return []

    counter = Counter()

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                about_val = item.get("schema:about", [])
                for kw in extract_about_values(about_val):
                    counter[kw] += 1
            except Exception:
                continue

    return counter.most_common()


def extract_suffixes_from_jsonl(input_jsonl_path: str, max_suffix_len: int = 3) -> list:
    """
    raw_metadata.jsonl からタイトルの末尾語彙 (接尾辞: 〜譜, 〜本, 〜録など) を抽出・カウント集計し、
    [(接尾辞, 出現件数), ...] の降順リストとして返します。
    """
    if not os.path.exists(input_jsonl_path):
        return []

    counter = Counter()

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                label_val = item.get("rdfs:label", item.get("schema:name", ""))
                if isinstance(label_val, list) and label_val:
                    label_str = str(label_val[0]).strip()
                else:
                    label_str = str(label_val).strip()

                if label_str:
                    clean_label = re.sub(r"[\s\(\)（）\[\]【】\d]+$", "", label_str)
                    if clean_label:
                        for l in range(1, max_suffix_len + 1):
                            if len(clean_label) >= l:
                                suf = clean_label[-l:]
                                counter[suf] += 1
            except Exception:
                continue

    return counter.most_common()


def suggest_ng_keywords_with_llm(
    current_ng_list: list, 
    sample_keywords: list, 
    target_keywords: list = None, 
    domain_definition: str = "", 
    provider: str = "local",
    api_base: str = DEFAULT_LLM_URL,
    api_key: str = "",
    model: str = DEFAULT_MODEL
) -> list:
    """
    【Gemini API / Local / OpenAI対応 高速ノイズサジェスト】
    目的キーワードと『無関係・異分野』なノイズ単語候補をデータセットから逆引き分析して選別・提案します。
    """
    if target_keywords is None:
        target_keywords = []

    sample_targets = target_keywords[:15]
    sample_ngs = current_ng_list[-20:] if len(current_ng_list) > 20 else current_ng_list
    sample_kws = sample_keywords[:40]

    system_prompt = (
        "あなたは文化資源メタデータの精査アシスタントです。\n"
        "ユーザーが提示した『目的キーワード』と『サンプル単語群』を比較し、"
        "目的キーワードのドメイン・ジャンルと【無関係・異分野】であると判断されるノイズ（除外対象）キーワード候補を25個程度選んで提案してください。\n"
        "出力は必ず純粋なJSON配列形式（例: [\"単語1\", \"単語2\"]）のみとしてください。"
    )

    user_prompt = (
        f"【目的キーワード】: {', '.join(sample_targets)}\n"
        f"【既知のNG例】: {', '.join(sample_ngs)}\n"
        f"【サンプル単語群】: {', '.join(sample_kws)}\n\n"
        "上記を踏まえ、無関係なノイズキーワード候補をJSON配列で返してください。"
    )

    ng_set = set(current_ng_list)
    ok_set = set(target_keywords)

    # --- 1. Google Gemini API ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            logger.warning("[Gemini Suggest Warning] Gemini API Key is missing.")
            return []

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                if isinstance(parsed, list):
                    return [k for k in parsed if k not in ng_set and k not in ok_set]
        except Exception as e:
            logger.warning(f"[Gemini Suggest Warning] {e}")
            print(f"[Gemini Suggest Warning] {e}")
            return []

    # --- 2. Local LLM / OpenAI ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1000
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=30)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [k for k in parsed if k not in ng_set and k not in ok_set]
        except Exception as e:
            logger.warning(f"[LLM Fast Suggest Warning] {e}")
            print(f"[LLM Fast Suggest Warning] {e}")
            return []

    return []


def suggest_related_keywords_by_base(
    base_keyword: str, 
    mode: str, 
    sample_keywords: list, 
    provider: str = "local",
    api_base: str = DEFAULT_LLM_URL,
    api_key: str = "",
    model: str = DEFAULT_MODEL
) -> list:
    """
    【Gemini API / Local / OpenAI対応 3点メニュー連想提案】
    特定の単一キーワード (base_keyword) を起点として、関連するノイズ(NG)または保持(OK)単語をGemini等で1秒サジェストします。
    """
    prioritized_kws = []
    other_kws = []
    base_chars = set(base_keyword)

    for kw in sample_keywords:
        if kw == base_keyword:
            continue
        if any(c in kw for c in base_chars if len(base_keyword) <= 2 or c not in "歴史研究図書"):
            prioritized_kws.append(kw)
        else:
            other_kws.append(kw)

    candidate_samples = (prioritized_kws + other_kws)[:30]

    if mode == "ng":
        mode_instruction = f"キーワード『{base_keyword}』と同類・類似する非対象（ノイズ）キーワード"
    else:
        mode_instruction = f"キーワード『{base_keyword}』と同一ジャンル・関連する保持キーワード"

    system_prompt = (
        "あなたは文化資源メタデータの精査アシスタントです。\n"
        f"提示されたサンプルの中から、{mode_instruction}を10個程度選んで提案してください。\n"
        "出力は必ず純粋なJSON配列形式（例: [\"単語1\", \"単語2\"]）のみとしてください。"
    )

    user_prompt = (
        f"【起点キーワード】: {base_keyword}\n"
        f"【サンプル単語群】: {', '.join(candidate_samples)}\n\n"
        f"{mode_instruction}をJSON配列で返してください。"
    )

    # --- 1. Google Gemini API ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return [kw for kw in candidate_samples if base_keyword != kw][:8]

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                resp_json = res.json()
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content.strip())
                if isinstance(parsed, list):
                    return [k for k in parsed if k != base_keyword]
        except Exception as e:
            logger.warning(f"[Gemini Base Suggest Warning] {e}")
            print(f"[Gemini Base Suggest Warning] {e}")

    # --- 2. Local LLM / OpenAI ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 800
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=20)
            if res.status_code == 200:
                choice_msg = res.json()["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

                json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [k for k in parsed if k != base_keyword]
        except Exception as e:
            logger.warning(f"[LLM Base Fast Suggest Warning] {e}")
            print(f"[LLM Base Fast Suggest Warning] {e}")

    return [kw for kw in candidate_samples if base_keyword != kw][:8]


def match_about_keyword(keyword: str, rule_target: str) -> bool:
    """
    Aboutキーワードとルールの合致判定。
    - NDCコードの場合: 階層的・前方一致（例: '76' は '768' や 'ndc9:768.1' にマッチするが '976' にはマッチしない）
    - 一般語彙の場合: 完全一致、または階層区切り（'--', ':', '/'）の前方一致
    """
    if not keyword or not rule_target:
        return False
    
    k_clean = str(keyword).strip()
    r_clean = str(rule_target).strip()
    
    if k_clean == r_clean:
        return True

    from components.ndc_utils import extract_ndc_number
    k_ndc = extract_ndc_number(k_clean)
    r_ndc = extract_ndc_number(r_clean)

    if k_ndc and r_ndc:
        if k_ndc == r_ndc:
            return True
        # 親コードが子コードを包含 (例: rule '76' / '760' -> item '768')
        if len(r_ndc) <= len(k_ndc):
            r_norm = r_ndc.rstrip('0') if r_ndc != '0' else r_ndc
            if k_ndc.startswith(r_norm):
                return True
        return False

    # 階層区切り記号をもつキーワードのプレフィックス判定
    for sep in ["--", " / ", " : ", "･", "・"]:
        if sep in k_clean:
            parts = k_clean.split(sep)
            if r_clean in parts or r_clean == parts[0]:
                return True

    # 部分一致フォールバック (ただしルール文字列が3文字以上の場合のみ安全に適用)
    if len(r_clean) >= 3 and r_clean in k_clean:
        return True

    return False


def run_about_filter(input_jsonl_path: str, rules_json_path: str, output_filtered_path: str, output_discarded_csv: str):
    """
    schema:about キーワード分類ルールに基づいてデータをフィルタリング。
    NG優先で除外判定し、残存データを出力します。
    """
    if not os.path.exists(input_jsonl_path):
        return 0, 0

    about_rules = {}
    if os.path.exists(rules_json_path):
        with open(rules_json_path, 'r', encoding='utf-8') as f:
            try:
                about_rules = json.load(f)
            except Exception:
                about_rules = {}

    ng_categories = set([cat for cat, status in about_rules.items() if status == "NG"])

    passed_count = 0
    discarded_records = []

    os.makedirs(os.path.dirname(output_filtered_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as in_f, \
         open(output_filtered_path, 'w', encoding='utf-8') as out_f:

        for line in in_f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            
            about_val = item.get("schema:about", [])
            extracted_kws = extract_about_values(about_val)

            has_ng = False
            matched_ng_cat = ""
            for kw in extracted_kws:
                for ng_cat in ng_categories:
                    if match_about_keyword(kw, ng_cat):
                        has_ng = True
                        matched_ng_cat = ng_cat
                        break
                if has_ng:
                    break

            if has_ng:
                label = item.get("rdfs:label", item.get("schema:name", "No Title"))
                title_str = label[0] if isinstance(label, list) and label else str(label)
                discarded_records.append({
                    "id": item.get("@id", item.get("id", "")),
                    "title": title_str,
                    "matched_ng": matched_ng_cat,
                    "reason": f"Aboutルール除外: {matched_ng_cat}"
                })
            else:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                passed_count += 1

    if discarded_records:
        import pandas as pd
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return passed_count, len(discarded_records)


def run_suffix_filter(input_jsonl_path: str, rules_json_path: str, output_filtered_path: str, output_discarded_csv: str):
    """末尾語彙（接尾辞）ルールに基づいてノイズタイトルを除外"""
    if not os.path.exists(input_jsonl_path):
        return 0, 0

    suffix_rules = {}
    if os.path.exists(rules_json_path):
        with open(rules_json_path, 'r', encoding='utf-8') as f:
            suffix_rules = json.load(f)

    ng_suffixes = set([suf for suf, status in suffix_rules.items() if status == "NG"])

    passed_count = 0
    discarded_records = []

    os.makedirs(os.path.dirname(output_filtered_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as in_f, \
         open(output_filtered_path, 'w', encoding='utf-8') as out_f:

        for line in in_f:
            if not line.strip():
                continue
            item = json.loads(line)
            
            label_val = item.get("rdfs:label", item.get("schema:name", ""))
            if isinstance(label_val, list) and label_val:
                label_str = str(label_val[0])
            else:
                label_str = str(label_val)

            has_ng = False
            matched_suffix = ""
            for suf in ng_suffixes:
                if label_str.endswith(suf):
                    has_ng = True
                    matched_suffix = suf
                    break

            if has_ng:
                discarded_records.append({
                    "id": item.get("@id", item.get("id", "")),
                    "title": label_str,
                    "matched_suffix": matched_suffix,
                    "reason": f"接尾辞ルール除外: 末尾「{matched_suffix}」"
                })
            else:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                passed_count += 1

    if discarded_records:
        import pandas as pd
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return passed_count, len(discarded_records)


def split_dataset_by_rules(
    input_jsonl_path: str,
    about_rules_path: str,
    ngram_rules_path: str,
    output_target_for_llm_jsonl: str,
    output_confirmed_ok_jsonl: str,
    output_discarded_csv: str
) -> tuple:
    """
    Aboutルールおよびタイトル文字列ルールに基づいてデータを3分類します。
    - 判定ポリシー: NG判定最優先 ＞ 残りの中でOK判定（LLMバイパス合格） ＞ 未判定（グレーゾーン・LLM投入）
    """
    if not os.path.exists(input_jsonl_path):
        return 0, 0, 0

    about_rules = {}
    if os.path.exists(about_rules_path):
        with open(about_rules_path, 'r', encoding='utf-8') as f:
            try:
                about_rules = json.load(f)
            except Exception:
                pass

    ngram_rules = {}
    if os.path.exists(ngram_rules_path):
        with open(ngram_rules_path, 'r', encoding='utf-8') as f:
            try:
                ngram_rules = json.load(f)
            except Exception:
                pass

    ng_about = set([cat for cat, status in about_rules.items() if status == "NG"])
    ok_about = set([cat for cat, status in about_rules.items() if status == "OK"])

    ng_ngram = set([pat for pat, status in ngram_rules.items() if status == "NG"])
    ok_ngram = set([pat for pat, status in ngram_rules.items() if status == "OK"])

    ok_count = 0
    ng_count = 0
    grey_count = 0

    discarded_records = []
    confirmed_ok_records = []

    os.makedirs(os.path.dirname(output_target_for_llm_jsonl), exist_ok=True)
    os.makedirs(os.path.dirname(output_confirmed_ok_jsonl), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as in_f, \
         open(output_target_for_llm_jsonl, 'w', encoding='utf-8') as grey_f:

        for line in in_f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue

            item_id = item.get("@id", item.get("id", ""))
            label_val = item.get("rdfs:label", item.get("schema:name", ""))
            if isinstance(label_val, list) and label_val:
                title_str = str(label_val[0])
            else:
                title_str = str(label_val)

            about_val = item.get("schema:about", [])
            extracted_about_kws = extract_about_values(about_val)

            # =================================================================
            # 1. NG判定（最優先）
            # =================================================================
            has_ng = False
            matched_ng_reason = ""

            for kw in extracted_about_kws:
                for ng_cat in ng_about:
                    if match_about_keyword(kw, ng_cat):
                        has_ng = True
                        matched_ng_reason = f"About NG: 「{ng_cat}」"
                        break
                if has_ng:
                    break

            if not has_ng:
                for pat in ng_ngram:
                    if pat in title_str:
                        has_ng = True
                        matched_ng_reason = f"タイトル NG: 「{pat}」"
                        break

            if has_ng:
                discarded_records.append({
                    "id": item_id,
                    "title": title_str,
                    "reason": matched_ng_reason
                })
                ng_count += 1
                continue

            # =================================================================
            # 2. OK判定 (NGなし ＆ OKあり -> LLMバイパス合格)
            # =================================================================
            has_ok = False
            matched_ok_reason = ""

            for kw in extracted_about_kws:
                for ok_cat in ok_about:
                    if match_about_keyword(kw, ok_cat):
                        has_ok = True
                        matched_ok_reason = f"About OK: 「{ok_cat}」"
                        break
                if has_ok:
                    break

            if not has_ok:
                for pat in ok_ngram:
                    if pat in title_str:
                        has_ok = True
                        matched_ok_reason = f"タイトル OK: 「{pat}」"
                        break

            if has_ok:
                confirmed_ok_records.append({
                    "id": item_id,
                    "title": title_str,
                    "is_target": True,
                    "reason": f"[ルール合格] {matched_ok_reason}",
                    "raw_item": item
                })
                ok_count += 1
                continue

            # =================================================================
            # 3. グレーゾーン (NGでもOKでもない -> LLM判定へ)
            # =================================================================
            grey_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            grey_count += 1

    # OK確定保存
    with open(output_confirmed_ok_jsonl, 'w', encoding='utf-8') as ok_f:
        for r in confirmed_ok_records:
            ok_f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # NG除外CSV保存
    if discarded_records:
        import pandas as pd
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return ok_count, ng_count, grey_count


# =============================================================================
# rdf:type (データ種別・リソース型) 抽出 ＆ フィルタリング
# =============================================================================

def extract_type_values(type_val) -> list:
    """
    rdf:type / type の生値（str, dict, list, またはそのネスト）から
    URI および短縮ラベル（日本語名）のペア [(full_uri, short_label), ...] を抽出します。
    """
    if not type_val:
        return []
    
    raw_list = type_val if isinstance(type_val, list) else [type_val]
    types_out = []
    
    for item in raw_list:
        if not item:
            continue
        if isinstance(item, dict):
            val = item.get("rdfs:label") or item.get("schema:name") or item.get("@id") or item.get("id") or ""
            if isinstance(val, list) and val:
                val = val[0]
            val_str = str(val).strip()
        else:
            val_str = str(item).strip()
            
        if not val_str:
            continue
            
        if val_str.startswith("http"):
            short_lbl = urllib.parse.unquote(val_str.split("/")[-1].split("#")[-1])
            types_out.append((val_str, short_lbl if short_lbl else val_str))
        else:
            types_out.append((val_str, val_str))
            
    return types_out


def extract_types_from_jsonl(input_jsonl_path: str) -> list:
    """
    jsonl から rdf:type を集計し、
    [(short_label, full_uri, count, sample_docs), ...] の降順リストを返します。
    """
    if not os.path.exists(input_jsonl_path):
        return []

    type_counts = Counter()
    type_to_uri = {}
    type_samples = {}

    with open(input_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            # タイトルの堅牢な取得 (rdfs:label, schema:name, title等)
            raw_title = rec.get('rdfs:label') or rec.get('schema:name') or rec.get('name') or rec.get('title') or ""
            if isinstance(raw_title, list) and raw_title:
                raw_title = raw_title[0]
            title = str(raw_title).strip() if raw_title else "（無題）"

            # IDの堅牢な取得 (@id, id)
            rec_id = rec.get('@id') or rec.get('id') or ""

            # 著者の堅牢な取得 (schema:creator)
            raw_creator = rec.get('schema:creator') or rec.get('creator') or ""
            if isinstance(raw_creator, list) and raw_creator:
                raw_creator = raw_creator[0]
            if isinstance(raw_creator, dict):
                raw_creator = raw_creator.get('rdfs:label') or raw_creator.get('name') or raw_creator.get('@id') or ""
            raw_creator_str = str(raw_creator).strip()
            if raw_creator_str.startswith("http"):
                creator = urllib.parse.unquote(raw_creator_str.split("/")[-1].split("#")[-1])
            else:
                creator = raw_creator_str

            # rdf:type の抽出
            t_val = rec.get('type') or rec.get('rdf_type') or rec.get('rdf:type')
            extracted = extract_type_values(t_val)

            doc_info = {"id": rec_id, "title": title, "creator": creator}

            if not extracted:
                type_counts["（未定義 / 種別なし）"] += 1
                type_to_uri["（未定義 / 種別なし）"] = ""
                if "（未定義 / 種別なし）" not in type_samples:
                    type_samples["（未定義 / 種別なし）"] = []
                type_samples["（未定義 / 種別なし）"].append(doc_info)
            else:
                for full_uri, short_lbl in extracted:
                    type_counts[short_lbl] += 1
                    type_to_uri[short_lbl] = full_uri
                    if short_lbl not in type_samples:
                        type_samples[short_lbl] = []
                    type_samples[short_lbl].append(doc_info)

    result = []
    for short_lbl, cnt in type_counts.most_common():
        result.append({
            "short_label": short_lbl,
            "full_uri": type_to_uri.get(short_lbl, ""),
            "count": cnt,
            "samples": type_samples.get(short_lbl, [])
        })

    return result


def load_type_rules(rules_path: str) -> dict:
    """type_rules.json を読み込み {'NG': set(), 'OK': set()} を返します"""
    rules = {"NG": set(), "OK": set()}
    if os.path.exists(rules_path):
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    rules["NG"] = set(data.get("NG", []))
                    rules["OK"] = set(data.get("OK", []))
        except Exception as e:
            logger.error(f"Error loading type_rules: {e}")
    return rules


def save_type_rules(rules_path: str, rules_dict: dict) -> bool:
    """type_rules を JSON 保存します"""
    try:
        os.makedirs(os.path.dirname(rules_path), exist_ok=True)
        data = {
            "NG": sorted(list(rules_dict.get("NG", set()))),
            "OK": sorted(list(rules_dict.get("OK", set())))
        }
        with open(rules_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving type_rules: {e}")
        return False


def apply_type_filter(input_jsonl_path: str, output_jsonl_path: str, type_rules_path: str) -> tuple:
    """
    type_rules.json の NG ルールに基づき、除外フィルタを適用して type_filtered.jsonl を生成します。
    戻り値: (total_count, passed_count, discarded_count)
    """
    rules = load_type_rules(type_rules_path)
    ng_types = rules["NG"]

    if not os.path.exists(input_jsonl_path):
        return 0, 0, 0

    total_cnt = 0
    passed_cnt = 0
    discarded_cnt = 0

    os.makedirs(os.path.dirname(output_jsonl_path), exist_ok=True)
    with open(input_jsonl_path, 'r', encoding='utf-8') as in_f, \
         open(output_jsonl_path, 'w', encoding='utf-8') as out_f:
        for line in in_f:
            if not line.strip():
                continue
            total_cnt += 1
            rec = json.loads(line)
            t_val = rec.get('type') or rec.get('rdf_type') or rec.get('rdf:type')
            extracted = extract_type_values(t_val)
            
            is_ng = False
            if not extracted:
                if "（未定義 / 種別なし）" in ng_types:
                    is_ng = True
            else:
                for full_uri, short_lbl in extracted:
                    if short_lbl in ng_types or full_uri in ng_types:
                        is_ng = True
                        break
            
            if is_ng:
                discarded_cnt += 1
            else:
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                passed_cnt += 1

    return total_cnt, passed_cnt, discarded_cnt


