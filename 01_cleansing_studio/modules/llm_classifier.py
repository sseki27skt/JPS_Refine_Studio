# -*- coding: utf-8 -*-
"""
LLMセマンティック自動判定 (グレーゾーン分類) モジュール (Gemini API / OpenAI / Local対応)
Stage 1: メタデータ高速並列判定
Stage 2: jpsearch.go.jp以外の外部リンク＆Web情報補強付き再判定
"""

import json
import os
import re
import time
import urllib.parse
import requests
from .logger import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


def extract_external_urls(raw_item: dict) -> list:
    """資料メタデータから jpsearch.go.jp 以外の外部URLを抽出"""
    urls = []
    
    source_info = raw_item.get("jps:sourceInfo", {})
    access_info = raw_item.get("jps:accessInfo", {})
    
    candidates = []
    if isinstance(source_info, dict):
        candidates.extend([
            source_info.get("schema:relatedLink"),
            source_info.get("rdfs:seeAlso"),
            source_info.get("schema:url")
        ])
    if isinstance(access_info, dict):
        candidates.extend([
            access_info.get("schema:relatedLink"),
            access_info.get("schema:url")
        ])
        
    candidates.extend([
        raw_item.get("schema:relatedLink"),
        raw_item.get("rdfs:seeAlso"),
        raw_item.get("schema:url")
    ])

    for cand in candidates:
        if not cand:
            continue
        if isinstance(cand, list):
            for u in cand:
                if isinstance(u, str):
                    urls.append(u)
        elif isinstance(cand, str):
            urls.append(cand)
            
    # 重複排除 ＆ jpsearch.go.jp 内部リンクの除外
    valid_urls = []
    seen = set()
    for u in urls:
        u_str = u.strip()
        if not u_str or u_str in seen:
            continue
        seen.add(u_str)
        # jpsearch.go.jp 自身はスキップ
        if "jpsearch.go.jp" in u_str:
            continue
        # 画像やmanifest等のバイナリ拡張子はスキップ
        parsed_path = urllib.parse.urlparse(u_str).path.lower()
        if parsed_path.endswith((".jpg", ".jpeg", ".png", ".gif", ".pdf", ".json", "manifest")):
            continue
        valid_urls.append(u_str)
        
    return valid_urls


def fetch_external_page_snippet(url: str, timeout: int = 5) -> str:
    """外部ページにアクセスし、タイトル・meta記述・本文テキストをクリーン抽出"""
    if not BeautifulSoup:
        return ""
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    try:
        # SSL警告の抑制
        try:
            requests.packages.urllib3.disable_warnings()
        except Exception:
            pass
            
        res = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
        if res.status_code != 200:
            return ""
            
        soup = BeautifulSoup(res.content, "html.parser")
        
        # 不要タグの除去
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "iframe"]):
            tag.extract()
            
        # meta description
        meta_desc = ""
        desc_tag = (soup.find("meta", attrs={"name": "description"}) or 
                    soup.find("meta", attrs={"property": "og:description"}) or 
                    soup.find("meta", attrs={"name": "og:description"}))
        if desc_tag and desc_tag.get("content"):
            meta_desc = desc_tag["content"].strip()
            
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
        
        # 本文クリーンテキストの抽出
        raw_text = soup.get_text(separator=" ", strip=True)
        clean_text = re.sub(r'\s+', ' ', raw_text)
        
        # ブロック画面・エラー画面の検出
        if "Just a moment" in clean_text or "アクセスが集中" in clean_text or "Enable JavaScript" in clean_text:
            return ""
            
        snippet_body = meta_desc if (meta_desc and len(meta_desc) > 10) else clean_text[:350]
        
        if snippet_body and len(snippet_body) > 15:
            return f"・外部サイト情報 ({url}): [{page_title}] {snippet_body[:300]}"
        elif page_title and len(page_title) > 3:
            return f"・外部サイト情報 ({url}): タイトル[{page_title}]"
            
    except Exception:
        pass
        
    return ""


def is_valid_japanese_snippet(text: str) -> bool:
    """テキスト内の日本語文字（ひらがな・カタカナ・漢字）の割合・件数を検証し、海外ノイズを除外"""
    if not text or len(text.strip()) < 10:
        return False
        
    lower_text = text.lower()
    # 海外コミュニティ掲示板・プロキシサイトのスパムキーワード除外
    spam_keywords = [
        "communauté orange", "décodeur tv", "découvrir les fonctionnalités", 
        "mon mail orange", "bonjour", "bonsoir", "stackoverrun", "qastack"
    ]
    for sk in spam_keywords:
        if sk in lower_text:
            return False
            
    # ひらがな・カタカナ・漢字の抽出と割合チェック
    jp_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
    if len(jp_chars) < 8:
        return False
        
    jp_ratio = len(jp_chars) / len(text)
    return jp_ratio >= 0.15


def fetch_web_fallback_snippet(title_text: str, num_results: int = 5) -> str:
    """
    旧バージョン (integrated_portal) に準拠・強化した DuckDuckGo ＆ Wikipedia 統合検索
    1. 「{title_text} 古典籍」または「{title_text} とは」でコンテキスト検索
    2. ヒットしなければ「{title_text}」単体で検索
    3. それでもヒットしなければ Wikipedia API を検索
    ※ 厳格な日本語判定により海外ノイズ・スパム掲示板を100%除外します。
    """
    if not title_text or title_text == "No Title":
        return "検索情報なし"

    clean_title = re.sub(r'[\(\)（）\[\]【】「」『』〈〉《》]', ' ', title_text).strip()
    if not clean_title:
        return "検索情報なし"

    # 1. DuckDuckGo 検索 (「タイトル とは」を第1優先)
    if DDGS:
        queries = [f"{clean_title} とは", f"{clean_title} 古典籍", clean_title]
        for q in queries:
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(q, region="jp-jp", max_results=num_results * 2))
                    if results:
                        output = []
                        for r in results:
                            t = r.get("title", "")
                            b = r.get("body", "")
                            if t and b:
                                combined = f"{t} {b}"
                                # 厳格な日本語判定 ＆ ノイズ除外
                                if not is_valid_japanese_snippet(combined):
                                    continue
                                output.append(f"・DuckDuckGo [{t}]: {b[:250]}")
                                if len(output) >= num_results:
                                    break
                        if output:
                            return "\n".join(output)
            except Exception:
                pass

    # 2. Wikipedia API をフォールバック検索
    try:
        wiki_url = f"https://ja.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(clean_title)}"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        res = requests.get(wiki_url, headers=headers, timeout=5)
        if res.status_code == 200:
            pages = res.json().get("query", {}).get("pages", {})
            for pid, pinfo in pages.items():
                if pid != "-1" and pinfo.get("extract"):
                    w_title = pinfo.get("title", "")
                    extract = pinfo.get("extract", "")
                    if extract:
                        return f"・Wikipedia [{w_title}]: {extract[:300]}"
    except Exception:
        pass

    return "検索情報なし"


def run_llm_semantic_classification(
    input_jsonl_path: str,
    output_judgments_path: str,
    domain_definition: str = "日本の古典籍における楽譜・音楽資料",
    provider: str = "gemini",
    api_base: str = "http://localhost:1234/v1",
    api_key: str = "",
    model: str = "gemini-3.6-flash",
    limit: int = None,
    max_workers: int = 4,
    progress_callback=None,
    should_stop=None
) -> tuple:
    """
    【DDG Web補強デフォルト化 ＆ 同一タイトル名寄せ一括判定 (Deduplication)】
    - 入力アイテムを「タイトル」で名寄せグループ化し、ユニークタイトルのみを抽出。
    - 各グループの代表1件に対し、DDG検索スニペット(上位5件) ＆ 外部リンク情報を全件デフォルト取得・プロンプト注入してLLM判定。
    - 判定結果(is_target, reason, external_info)をグループ内の全資料へ一括展開・書き出し。
    - 返り値: (accepted_count, rejected_count, unknown_count, total_items, unique_count)
    """
    if not os.path.exists(input_jsonl_path):
        return 0, 0, 0, 0, 0

    os.makedirs(os.path.dirname(output_judgments_path), exist_ok=True)

    items = []
    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.strip():
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue

    total_items = len(items)

    # 既存の判定結果ログが存在する場合、判定済みの ID / タイトル を読み込んでスキップ用セットを作成
    already_judged_ids = set()
    already_judged_titles = set()
    existing_records_dict = {}

    if os.path.exists(output_judgments_path):
        with open(output_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        did = data.get("id")
                        dtitle = data.get("title")
                        if did:
                            already_judged_ids.add(did)
                            existing_records_dict[did] = data
                        if dtitle:
                            clean_t = re.sub(r'[\s　\(\)（）\[\]【】「」『』\.,:：［］;!\?/\-_\d・―〜〈〉《》“”‘’\+=★☆◆◇▲△▼▽○●◎／]', '', str(dtitle))
                            if clean_t:
                                already_judged_titles.add(clean_t)
                    except Exception:
                        pass

    # 1. タイトルの正規化と名寄せグループ化 (Deduplication)
    from collections import defaultdict
    grouped_by_title = defaultdict(list)
    for idx, item in enumerate(items):
        label = item.get("rdfs:label", item.get("schema:name", f"No Title_{idx}"))
        title_str = label[0] if isinstance(label, list) and label else str(label)
        clean_title = re.sub(r'[\s　\(\)（）\[\]【】「」『』\.,:：［］;!\?/\-_\d・―〜〈〉《》“”‘’\+=★☆◆◇▲△▼▽○●◎／]', '', title_str)
        key = clean_title if clean_title else title_str
        grouped_by_title[key].append((idx, item, title_str))

    # 各グループから最も説明文が長いアイテムを代表として選出
    representative_items = []
    for key, item_group in grouped_by_title.items():
        best_item_entry = max(
            item_group,
            key=lambda x: len(str(x[1].get("schema:description", "")))
        )
        representative_items.append((key, best_item_entry, item_group))

    total_unique = len(representative_items)

    # 未判定の代表アイテムのみを抽出（すでに判定済みの同名・同IDグループは自動スキップ）
    unjudged_representative_items = []
    for rep in representative_items:
        key, (best_idx, rep_item, item_group), item_group = rep
        is_already_done = False
        if key in already_judged_titles:
            is_already_done = True
        else:
            for orig_idx, orig_item, orig_title in item_group:
                orig_id = orig_item.get("@id", orig_item.get("id", f"item_{orig_idx}"))
                if orig_id in already_judged_ids:
                    is_already_done = True
                    break
        if not is_already_done:
            unjudged_representative_items.append(rep)

    # 件数制限 (limit) は未判定データに対して適用
    if limit:
        targets_to_process = unjudged_representative_items[:limit]
    else:
        targets_to_process = unjudged_representative_items
    accepted_count = 0
    rejected_count = 0
    unknown_count = 0

    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        f"【対象ドメイン定義】: {domain_definition}\n\n"
        "提示された書誌メタデータおよび【Web/外部検索補足情報】（原典サイトの解説やDDG/Wikipedia検索要約）を総合的に精査し、"
        "対象ドメイン資料として適合するか判定してください。完全に適合するものはtrue、完全に適合しないものはfalse、判断に迷うものはnullとしてください。必ず純粋なJSONフォーマットのみを出力してください。\n"
        "【出力形式】:\n"
        "{\n"
        '  "is_target": true または false または null,\n'
        '  "reason": "Web/外部補足情報やメタデータのどこに依拠して判断したかの簡潔な理由"\n'
        "}\n"
    )

    eff_workers = 1 if provider.lower() in ["local", "lmstudio"] else max(1, max_workers)

    def process_representative_title(idx_rep):
        rep_idx, (key, (best_idx, rep_item, item_group), item_group) = idx_rep
        title = item_group[0][2]  # オリジナルタイトル名
        
        desc_val = rep_item.get("schema:description", "")
        desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)

        # 1. 外部リンク情報取得
        ext_urls = extract_external_urls(rep_item)
        snippets = []
        for url in ext_urls[:2]:
            snip = fetch_external_page_snippet(url, timeout=5)
            if snip and len(snip.strip()) > 10:
                snippets.append(snip)

        # 2. DDG Web/Wikipedia 補強検索 (デフォルト有効: 上位5件)
        fallback_snip = fetch_web_fallback_snippet(title, num_results=5)
        if fallback_snip and fallback_snip != "検索情報なし":
            snippets.append(fallback_snip)

        external_info_text = "\n".join(snippets) if snippets else "補足情報なし"

        user_prompt = (
            f"タイトル: {title}\n"
            f"詳細/説明文: {desc[:400] if desc else '記述なし'}\n"
            f"分類/ジャンル: {rep_item.get('schema:genre', 'なし')}\n\n"
            f"【Web/外部検索補足情報 (DDG / 外部アーカイブ)】:\n{external_info_text}\n"
        )

        judgment = _classify_single_item(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            api_base=api_base,
            api_key=api_key,
            model=model
        )

        is_target = judgment.get("is_target")
        reason = judgment.get("reason", "判定完了")

        # 同一タイトルの全資料へ判定結果を一括適用
        group_results = []
        for orig_idx, orig_item, orig_title in item_group:
            orig_id = orig_item.get("@id", orig_item.get("id", f"item_{orig_idx}"))
            res_obj = {
                "index": orig_idx,
                "id": orig_id,
                "title": orig_title,
                "is_target": is_target,
                "reason": f"[DDGWeb補強/名寄せ] {reason}",
                "external_info": external_info_text,
                "raw_item": orig_item,
                "source_stage": "LLM (DDG Web補強/名寄せ適用)"
            }
            group_results.append(res_obj)

        return rep_idx, title, is_target, reason, group_results

    all_expanded_results = {}
    completed_unique = 0

    if eff_workers > 1:
        with ThreadPoolExecutor(max_workers=eff_workers) as executor:
            future_to_rep = {
                executor.submit(process_representative_title, (i, rep_entry)): i 
                for i, rep_entry in enumerate(targets_to_process)
            }
            for future in as_completed(future_to_rep):
                if should_stop and should_stop():
                    # 停止要求がある場合、未完了タスクをキャンセルしてループ中断
                    for f in future_to_rep:
                        f.cancel()
                    break

                rep_idx, title, is_target, reason, group_results = future.result()
                completed_unique += 1
                
                for r in group_results:
                    all_expanded_results[r["index"]] = r
                    if r["is_target"] is True:
                        accepted_count += 1
                    elif r["is_target"] is False:
                        rejected_count += 1
                    else:
                        unknown_count += 1

                if progress_callback:
                    progress_callback(completed_unique, len(targets_to_process), f"{title} (他{len(group_results)-1}件同タイトル)", is_target, reason)
    else:
        for i, rep_entry in enumerate(targets_to_process):
            if should_stop and should_stop():
                break

            rep_idx, title, is_target, reason, group_results = process_representative_title((i, rep_entry))
            completed_unique += 1

            for r in group_results:
                all_expanded_results[r["index"]] = r
                if r["is_target"] is True:
                    accepted_count += 1
                elif r["is_target"] is False:
                    rejected_count += 1
                else:
                    unknown_count += 1

            if progress_callback:
                progress_callback(completed_unique, len(targets_to_process), f"{title} (他{len(group_results)-1}件同タイトル)", is_target, reason)

    # 既存の判定レコードと今回新しく判定されたレコードを統合してログ保存
    final_records_dict = dict(existing_records_dict)
    for idx, r in all_expanded_results.items():
        did = r.get("id")
        if did:
            final_records_dict[did] = r

    with open(output_judgments_path, 'w', encoding='utf-8') as f:
        for r in final_records_dict.values():
            clean_r = {k: v for k, v in r.items() if k != "index"}
            f.write(json.dumps(clean_r, ensure_ascii=False) + "\n")

    return accepted_count, rejected_count, unknown_count, total_items, total_unique


def run_stage2_llm_classification(
    judgments_jsonl_path: str,
    domain_definition: str = "日本の古典籍における楽譜・音楽資料",
    provider: str = "gemini",
    api_base: str = "http://localhost:1234/v1",
    api_key: str = "",
    model: str = "gemini-3.6-flash",
    max_workers: int = 2,
    progress_callback=None,
    should_stop=None
) -> tuple:
    """
    [Stage 2] Stage 1で判定不能 (is_target == null) になった項目に対し、
    jpsearch.go.jp以外の外部リンクまたはWeb検索スニペットを補強してLLM再判定を行います。
    """
    if not os.path.exists(judgments_jsonl_path):
        return 0, 0, 0

    all_records = []
    unknown_indices = []

    with open(judgments_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if line.strip():
                try:
                    data = json.loads(line)
                    all_records.append(data)
                    if data.get("is_target") is None:
                        unknown_indices.append(idx)
                except Exception:
                    continue

    total_unknown = len(unknown_indices)
    if total_unknown == 0:
        return 0, 0, 0

    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        f"【対象ドメイン定義】: {domain_definition}\n\n"
        "提示された書誌メタデータおよび【外部補足情報】（原典サイトの解説やWeb要約）を総合的に精査し、"
        "対象ドメイン資料として適合するか判定してください。完全に適合するものはtrue、完全に適合しないものはfalse、判断に迷うものはnullとしてください。必ず純粋なJSONフォーマットのみを出力してください。\n"
        "【出力形式】:\n"
        "{\n"
        '  "is_target": true または false または null,\n'
        '  "reason": "外部補足情報やメタデータのどこに依拠して判断したかの簡潔な理由"\n'
        "}\n"
    )

    eff_workers = 1 if provider.lower() in ["local", "lmstudio"] else max(1, max_workers)

    def process_unknown_item(idx_entry):
        order, record_idx = idx_entry
        record = all_records[record_idx]
        raw_item = record.get("raw_item", {})
        title = record.get("title", "No Title")
        
        desc_val = raw_item.get("schema:description", "")
        desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)

        # 1. jpsearch.go.jp 以外の外部リンクを取得
        ext_urls = extract_external_urls(raw_item)
        snippets = []
        
        for url in ext_urls[:2]:
            snip = fetch_external_page_snippet(url, timeout=5)
            if snip and len(snip.strip()) > 10:
                snippets.append(snip)

        # 2. スニペットが空、または極めて短い・タイトル名しか取れていない場合はWeb/Wikipedia検索で補強
        need_fallback = False
        if not snippets:
            need_fallback = True
        else:
            combined = " ".join(snippets)
            if len(combined) < 60 or "国立国会図書館" in combined:
                need_fallback = True
                
        if need_fallback:
            fallback_snip = fetch_web_fallback_snippet(title)
            if fallback_snip and fallback_snip != "検索情報なし":
                snippets.append(fallback_snip)

        external_info_text = "\n".join(snippets) if snippets else "補足情報なし"

        user_prompt = (
            f"タイトル: {title}\n"
            f"詳細/説明文: {desc[:400] if desc else '記述なし'}\n"
            f"分類/ジャンル: {raw_item.get('schema:genre', 'なし')}\n\n"
            f"【外部補足情報】:\n{external_info_text}\n"
        )

        judgment = _classify_single_item(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            api_base=api_base,
            api_key=api_key,
            model=model
        )

        is_target = judgment.get("is_target")
        reason = judgment.get("reason", "Stage 2 完了")

        # レコード更新
        record["is_target"] = is_target
        record["reason"] = f"[Stage 2補強] {reason}"
        record["external_info"] = external_info_text
        record["source_stage"] = "Stage 2 (Web/外部情報補強)"
        return order, record_idx, record

    resolved_acc = 0
    resolved_rej = 0
    remaining_unk = 0
    completed_counter = 0

    if eff_workers > 1:
        with ThreadPoolExecutor(max_workers=eff_workers) as executor:
            future_to_idx = {
                executor.submit(process_unknown_item, (i, record_idx)): i 
                for i, record_idx in enumerate(unknown_indices)
            }
            for future in as_completed(future_to_idx):
                if should_stop and should_stop():
                    for f in future_to_idx:
                        f.cancel()
                    break

                order, record_idx, updated_record = future.result()
                all_records[record_idx] = updated_record
                completed_counter += 1

                if updated_record["is_target"] is True:
                    resolved_acc += 1
                elif updated_record["is_target"] is False:
                    resolved_rej += 1
                else:
                    remaining_unk += 1

                if progress_callback:
                    progress_callback(
                        completed_counter, 
                        total_unknown, 
                        updated_record["title"], 
                        updated_record["is_target"], 
                        updated_record["reason"]
                    )
    else:
        for i, record_idx in enumerate(unknown_indices):
            if should_stop and should_stop():
                break

            order, record_idx, updated_record = process_unknown_item((i, record_idx))
            all_records[record_idx] = updated_record
            completed_counter += 1

            if updated_record["is_target"] is True:
                resolved_acc += 1
            elif updated_record["is_target"] is False:
                resolved_rej += 1
            else:
                remaining_unk += 1

            if progress_callback:
                progress_callback(
                    completed_counter, 
                    total_unknown, 
                    updated_record["title"], 
                    updated_record["is_target"], 
                    updated_record["reason"]
                )

    # 判決ファイル上書き書き出し
    with open(judgments_jsonl_path, 'w', encoding='utf-8') as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return resolved_acc, resolved_rej, remaining_unk


def _classify_single_item(system_prompt: str, user_prompt: str, provider: str, api_base: str, api_key: str, model: str, max_retries: int = 3) -> dict:
    """単一アイテムのLLM判定リクエスト (429自動リトライ付き)"""
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return {"is_target": None, "reason": "Gemini APIキー未設定"}

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json"
            }
        }

        for attempt in range(max_retries):
            try:
                res = requests.post(url, json=payload, timeout=30)
                if res.status_code == 200:
                    text_content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return _parse_json_response(text_content)
                elif res.status_code == 429:
                    wait_sec = 2 ** (attempt + 1)
                    time.sleep(wait_sec)
                    continue
                else:
                    return {"is_target": None, "reason": f"Gemini API Status Code: {res.status_code}"}
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"is_target": None, "reason": f"Gemini API Error: {e}"}
                time.sleep(1)

        return {"is_target": None, "reason": "Gemini API Rate limit (429)"}

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
            "max_tokens": 500
        }

        for attempt in range(max_retries):
            try:
                url = f"{api_base.rstrip('/')}/chat/completions"
                res = requests.post(url, json=payload, headers=req_headers, timeout=30)
                if res.status_code == 200:
                    choice_msg = res.json()["choices"][0]["message"]
                    content = choice_msg.get("content") or choice_msg.get("reasoning_content", "")
                    return _parse_json_response(content)
                elif res.status_code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                else:
                    return {"is_target": None, "reason": f"API Status Code: {res.status_code}"}
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"is_target": None, "reason": f"API Error: {e}"}
                time.sleep(1)

    return {"is_target": None, "reason": "判定不能"}


def _parse_json_response(raw_text: str) -> dict:
    """Markdown装飾（```json ... ```）を除去して構造化JSON辞書を抽出"""
    if not raw_text:
        return {"is_target": None, "reason": "レスポンスが空です"}
    cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    return {"is_target": None, "reason": f"JSON解析失敗: {raw_text[:60]}"}
