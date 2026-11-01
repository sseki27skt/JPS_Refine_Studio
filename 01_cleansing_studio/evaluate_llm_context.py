# -*- coding: utf-8 -*-
"""
カメラレディ論文用：LLMコンテキスト拡張アブレーション検証スクリプト
- 正例100件：scores.jsonl の「判定保留（グレーゾーン）」ユニークタイトルからランダム抽出
- 負例100件：既存ワークスペースから多義語ノイズ（系譜・年譜、画譜・書譜、硯譜・介譜等の博物譜、音楽研究書・器物等）を各25件ずつ計100件抽出
- 3条件比較：
  Condition 1 (no_context): コンテキスト拡張なし（書誌メタデータのみ）
  Condition 2 (unrestricted_web): 日本語縛りなしコンテキスト拡張（region="wt-wt", 日本語文字比率フィルタなし）
  Condition 3 (jp_filtered_web): 日本語縛りありコンテキスト拡張（本番環境: region="jp-jp", 「とは」検索, is_valid_japanese_snippet 適用）
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# モジュールパスの追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from modules.llm_classifier import (
    _classify_single_item,
    extract_external_urls,
    fetch_external_page_snippet,
    fetch_web_fallback_snippet,
    is_valid_japanese_snippet,
)

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

BENCHMARK_DIR = os.path.join(PROJECT_ROOT, "data", "benchmark_llm_200")
BENCHMARK_DATASET_PATH = os.path.join(BENCHMARK_DIR, "benchmark_200_with_contexts.jsonl")
RESULTS_JSON_PATH = os.path.join(BENCHMARK_DIR, "ablation_results_summary.json")
RESULTS_CSV_PATH = os.path.join(BENCHMARK_DIR, "ablation_results_detail.csv")
REPORT_MD_PATH = os.path.join(BENCHMARK_DIR, "ablation_evaluation_report.md")


def normalize_title(title_str: str) -> str:
    clean_t = re.sub(
        r"[\s　\(\)（）\[\]【】「」『』\.,:：［］;!\?/\-_\d・―〜〈〉《》“”‘’\+=★☆◆◇▲△▼▽○●◎／]",
        "",
        str(title_str),
    )
    return clean_t if clean_t else str(title_str)


def get_item_title(item: dict) -> str:
    t = item.get("rdfs:label", item.get("schema:name", ""))
    if isinstance(t, list):
        t = t[0] if t else ""
    return str(t).strip()


def get_item_description(item: dict) -> str:
    desc_val = item.get("schema:description", "")
    if isinstance(desc_val, list):
        return " / ".join(str(x) for x in desc_val if x)
    return str(desc_val)


def fetch_unrestricted_web_snippet(title_text: str, num_results: int = 5) -> str:
    """
    Condition 2: 日本語縛りなしのWeb検索スニペット取得
    - region="wt-wt" (全世界対象)
    - クエリはタイトルそのまま（「とは」を付加しない）
    - is_valid_japanese_snippet による日本語文字比率フィルタを行わない
    """
    if not title_text or title_text == "No Title":
        return "検索情報なし"

    clean_title = re.sub(r"[\(\)（）\[\]【】「」『』〈〉《》]", " ", title_text).strip()
    if not clean_title:
        return "検索情報なし"

    if DDGS:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(clean_title, region="wt-wt", max_results=num_results))
                if results:
                    output = []
                    for r in results:
                        t = r.get("title", "")
                        b = r.get("body", "")
                        if t and b:
                            output.append(f"・DuckDuckGo [{t}]: {b[:250]}")
                            if len(output) >= num_results:
                                break
                    if output:
                        return "\n".join(output)
        except Exception:
            pass

    return "検索情報なし"


def build_benchmark_200(seed: int = 42) -> list:
    """
    正例100件 + 負例100件の合計200件ベンチマークデータセットを構築
    """
    random.seed(seed)
    scores_path = os.path.join(PROJECT_ROOT, "scores.jsonl")
    with open(scores_path, "r", encoding="utf-8") as f:
        scores = [json.loads(line) for line in f if line.strip()]

    pos_ids = {s.get("@id") for s in scores}
    pos_norm_titles = {normalize_title(get_item_title(s)) for s in scores}

    # 1. 正例100件：判定保留（グレーゾーン）をユニークタイトル化してランダムに100件抽出
    grey_scores = [s for s in scores if "判定保留" in str(s.get("review_reasons", ""))]
    grouped_pos = defaultdict(list)
    for s in grey_scores:
        key = normalize_title(get_item_title(s))
        grouped_pos[key].append(s)

    rep_pos = []
    for key, grp in grouped_pos.items():
        best = max(grp, key=lambda x: len(get_item_description(x)))
        rep_pos.append(best)

    # ソートしてからシード固定サンプリング（完全な再現性担保）
    rep_pos.sort(key=lambda x: str(x.get("@id", "")))
    sampled_pos = random.sample(rep_pos, 100)

    benchmark_items = []
    for s in sampled_pos:
        title = get_item_title(s)
        has_fu = "譜" in title
        subcat = "POS_譜あり" if has_fu else "POS_譜なし(隠れ楽譜)"
        benchmark_items.append({
            "id": s.get("@id"),
            "title": title,
            "ground_truth": True,
            "category": subcat,
            "has_fu_in_title": has_fu,
            "raw_item": s,
        })

    # 2. 負例100件：既存ワークスペースから4カテゴリ×25件の紛らわしい非楽譜を抽出
    seen_neg_titles = set(pos_norm_titles)
    seen_neg_ids = set(pos_ids)

    # (A) score4gagaku で人間が不合格にした17件（音楽研究書・解説書・非伝統音楽・発酵文化譜など）
    s4g_raw_path = os.path.join(
        PROJECT_ROOT, "data", "workspaces", "score4gagaku", "data", "raw_metadata.jsonl"
    )
    cat4_research_and_borderline = []
    if os.path.exists(s4g_raw_path):
        with open(s4g_raw_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                did = str(d.get("@id", ""))
                if did in seen_neg_ids or not did.startswith("https://jpsearch.go.jp/data/"):
                    continue
                t = get_item_title(d)
                nt = normalize_title(t)
                if not nt or nt in seen_neg_titles:
                    continue
                # 明確に研究書・解説書・非古典楽譜であるものを選別
                if any(
                    kw in t
                    for kw in [
                        "研究",
                        "乳酸発酵",
                        "クラシック",
                        "ガイドブック",
                        "音楽考",
                        "目録",
                        "とり方",
                        "文化の伏流",
                    ]
                ):
                    cat4_research_and_borderline.append(d)
                    seen_neg_titles.add(nt)
                    seen_neg_ids.add(did)

    # (B) gagaku_score の target_for_llm.jsonl (ルールフィルタを通過したグレーゾーン非楽譜) から抽出
    gs_llm_path = os.path.join(
        PROJECT_ROOT, "data", "workspaces", "gagaku_score", "data", "target_for_llm.jsonl"
    )
    cat1_genealogy = []  # 系譜・家譜・年譜・世譜 (25件)
    cat2_art_calligraphy = []  # 画譜・図譜・書譜・印譜・紋譜 (25件)
    cat3_natural_history_hobby = []  # 硯譜・介譜・花譜・茶譜・香譜・酒譜・棋譜等の博物・趣味譜 (25件)

    pat_cat1 = re.compile(r"(系譜|家譜|年譜|世譜|藩翰譜|脈譜|宗譜|族譜|史譜)")
    pat_cat2 = re.compile(r"(画譜|畫譜|図譜|圖譜|書譜|印譜|紋譜|法帖|絵譜)")
    pat_cat3 = re.compile(
        r"(硯譜|介譜|貝譜|花譜|朝顔譜|桜譜|櫻譜|梅譜|菊譜|竹譜|菌譜|魚譜|虫譜|鳥譜|刀譜|剣譜|泉譜|銭譜|茶譜|香譜|棋譜|酒譜|食譜)"
    )
    pat_cat4_extra = re.compile(
        r"(愛用の龍笛|鳩笛|ゴム製笛|比叡山延暦寺之図|近江地図|名古屋図|大絵図|音楽史|邦楽年表|楽器図鑑|雅楽の|声明の研究)"
    )

    with open(gs_llm_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            did = str(d.get("@id", ""))
            if not did.startswith("https://jpsearch.go.jp/data/") or did in seen_neg_ids:
                continue
            t = get_item_title(d)
            nt = normalize_title(t)
            if not nt or nt in seen_neg_titles:
                continue
            # 音楽・楽譜の可能性が少しでもある語を除外（安全のため）
            if any(
                music_kw in t
                for music_kw in ["楽譜", "三味線", "箏", "琵琶", "尺八", "笙", "篳篥", "工工四", "唱歌", "催馬楽", "神楽", "声明", "郢曲"]
            ) and not pat_cat4_extra.search(t):
                continue

            if pat_cat1.search(t):
                cat1_genealogy.append(d)
                seen_neg_titles.add(nt)
                seen_neg_ids.add(did)
            elif pat_cat2.search(t):
                cat2_art_calligraphy.append(d)
                seen_neg_titles.add(nt)
                seen_neg_ids.add(did)
            elif pat_cat3.search(t):
                cat3_natural_history_hobby.append(d)
                seen_neg_titles.add(nt)
                seen_neg_ids.add(did)
            elif pat_cat4_extra.search(t):
                cat4_research_and_borderline.append(d)
                seen_neg_titles.add(nt)
                seen_neg_ids.add(did)

    # もし cat4 が25件に満たない場合、raw_metadata.jsonl から音楽研究書・器物・明確な非楽譜を補充
    if len(cat4_research_and_borderline) < 25:
        gs_raw_path = os.path.join(
            PROJECT_ROOT, "data", "workspaces", "gagaku_score", "data", "raw_metadata.jsonl"
        )
        pat_cat4_raw = re.compile(
            r"(音楽研究|音楽史|楽器の研究|浄瑠璃史|歌舞伎年表|能楽研究|雅楽の研究|邦楽の|三味線の研究|尺八の歴史|琵琶の研究)"
        )
        with open(gs_raw_path, "r", encoding="utf-8") as f:
            for line in f:
                if len(cat4_research_and_borderline) >= 35:
                    break
                if not line.strip():
                    continue
                d = json.loads(line)
                did = str(d.get("@id", ""))
                if not did.startswith("https://jpsearch.go.jp/data/") or did in seen_neg_ids:
                    continue
                t = get_item_title(d)
                nt = normalize_title(t)
                if not nt or nt in seen_neg_titles:
                    continue
                if pat_cat4_raw.search(t) and "譜" not in t:
                    cat4_research_and_borderline.append(d)
                    seen_neg_titles.add(nt)
                    seen_neg_ids.add(did)

    # 各カテゴリから25件ずつ抽出（計100件）
    random.seed(seed)
    s_cat1 = random.sample(cat1_genealogy, 25)
    s_cat2 = random.sample(cat2_art_calligraphy, 25)
    s_cat3 = random.sample(cat3_natural_history_hobby, 25)
    s_cat4 = cat4_research_and_borderline[:25]

    neg_groups = [
        ("NEG_1_系譜・年譜・世譜", s_cat1),
        ("NEG_2_画譜・書譜・印譜・紋譜", s_cat2),
        ("NEG_3_博物・器物・趣味譜(硯譜・介譜等)", s_cat3),
        ("NEG_4_音楽研究書・器物・境界ノイズ", s_cat4),
    ]

    for cat_name, items in neg_groups:
        for d in items:
            title = get_item_title(d)
            benchmark_items.append({
                "id": d.get("@id"),
                "title": title,
                "ground_truth": False,
                "category": cat_name,
                "has_fu_in_title": "譜" in title,
                "raw_item": d,
            })

    return benchmark_items


def enrich_contexts_for_benchmark(benchmark_items: list, max_workers: int = 6) -> list:
    """
    200件それぞれに対し、
    - external_page_snippet (原典リンク)
    - ddg_unrestricted_snippet (Condition 2: 日本語縛りなし)
    - ddg_jp_filtered_snippet (Condition 3: 日本語縛りあり + Wikipediaフォールバック)
    を並列取得してキャッシュする。
    """
    # 既存の score4gagaku/data/llm_judgments.jsonl があれば参考用にロード
    os.makedirs(BENCHMARK_DIR, exist_ok=True)

    # 既にキャッシュ済みのアイテムがあれば再利用
    cached_by_id = {}
    if os.path.exists(BENCHMARK_DATASET_PATH):
        with open(BENCHMARK_DATASET_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    if (
                        "context_unrestricted" in d
                        and "context_jp_filtered" in d
                    ):
                        cached_by_id[d["id"]] = d

    def process_one(idx_item):
        idx, item = idx_item
        iid = item["id"]
        if iid in cached_by_id:
            return idx, cached_by_id[iid]

        raw_item = item["raw_item"]
        title = item["title"]

        # 1. 原典外部リンクのスニペット取得
        ext_urls = extract_external_urls(raw_item)
        ext_snippets_unrestricted = []
        ext_snippets_jp = []
        for url in ext_urls[:2]:
            snip = fetch_external_page_snippet(url, timeout=5)
            if snip and len(snip.strip()) > 10:
                ext_snippets_unrestricted.append(snip)
                if is_valid_japanese_snippet(snip):
                    ext_snippets_jp.append(snip)

        # 2. Condition 2: 日本語縛りなし Web検索 (region="wt-wt", フィルタなし)
        unrestricted_ddg = fetch_unrestricted_web_snippet(title, num_results=5)
        cond2_parts = list(ext_snippets_unrestricted)
        if unrestricted_ddg and unrestricted_ddg != "検索情報なし":
            cond2_parts.append(unrestricted_ddg)
        context_unrestricted = "\n".join(cond2_parts) if cond2_parts else "補足情報なし"

        # 3. Condition 3: 日本語縛りあり Web検索 (region="jp-jp", 「とは」検索, is_valid_japanese_snippet, Wikipedia)
        jp_ddg = fetch_web_fallback_snippet(title, num_results=5)
        cond3_parts = list(ext_snippets_jp)
        if jp_ddg and jp_ddg != "検索情報なし":
            cond3_parts.append(jp_ddg)
        context_jp_filtered = "\n".join(cond3_parts) if cond3_parts else "補足情報なし"

        # Condition 2 に混入した非日本語スニペットの数をカウント
        non_jp_lines_in_cond2 = 0
        if unrestricted_ddg and unrestricted_ddg != "検索情報なし":
            for line in unrestricted_ddg.split("\n"):
                if line.strip() and not is_valid_japanese_snippet(line):
                    non_jp_lines_in_cond2 += 1

        enriched = dict(item)
        enriched["ext_urls_count"] = len(ext_urls)
        enriched["has_ext_url_snippet"] = len(ext_snippets_jp) > 0
        enriched["has_ddg_unrestricted"] = unrestricted_ddg != "検索情報なし"
        enriched["has_ddg_jp_filtered"] = jp_ddg != "検索情報なし" and "DuckDuckGo" in jp_ddg
        enriched["has_wikipedia_jp"] = jp_ddg != "検索情報なし" and "Wikipedia" in jp_ddg
        enriched["non_jp_lines_in_cond2"] = non_jp_lines_in_cond2
        enriched["context_none"] = "補足情報なし"
        enriched["context_unrestricted"] = context_unrestricted
        enriched["context_jp_filtered"] = context_jp_filtered
        return idx, enriched

    results = [None] * len(benchmark_items)
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(process_one, (i, item)): i for i, item in enumerate(benchmark_items)
        }
        for fut in as_completed(futures):
            idx, enriched = fut.result()
            results[idx] = enriched
            completed += 1
            if completed % 20 == 0 or completed == len(benchmark_items):
                print(f"[Context Fetch] {completed}/{len(benchmark_items)} completed")

    with open(BENCHMARK_DATASET_PATH, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Saved enriched benchmark dataset to: {BENCHMARK_DATASET_PATH}")
    return results


def build_prompts(item: dict, condition: str, domain_definition: str) -> tuple:
    raw_item = item["raw_item"]
    title = item["title"]
    desc = get_item_description(raw_item)
    genre = raw_item.get("schema:genre", "なし")

    if condition == "no_context":
        system_prompt = (
            "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
            f"【対象ドメイン定義】: {domain_definition}\n\n"
            "提示された書誌メタデータのみを精査し、"
            "対象ドメイン資料として適合するか判定してください。完全に適合するものはtrue、完全に適合しないものはfalse、判断に迷うものはnullとしてください。必ず純粋なJSONフォーマットのみを出力してください。\n"
            "【出力形式】:\n"
            "{\n"
            '  "is_target": true または false または null,\n'
            '  "reason": "メタデータのどこに依拠して判断したかの簡潔な理由"\n'
            "}\n"
        )
        user_prompt = (
            f"タイトル: {title}\n"
            f"詳細/説明文: {desc[:400] if desc else '記述なし'}\n"
            f"分類/ジャンル: {genre}\n"
        )
    else:
        ext_text = (
            item["context_unrestricted"]
            if condition == "unrestricted_web"
            else item["context_jp_filtered"]
        )
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
        user_prompt = (
            f"タイトル: {title}\n"
            f"詳細/説明文: {desc[:400] if desc else '記述なし'}\n"
            f"分類/ジャンル: {genre}\n\n"
            f"【Web/外部検索補足情報 (DDG / 外部アーカイブ)】:\n{ext_text}\n"
        )
    return system_prompt, user_prompt


def compute_metrics(items: list, pred_key: str) -> dict:
    """
    2種類の評価指標を算出：
    1. Strict (End-to-End): null を未採択/不正解として扱う場合の TP, FP, FN, TN, Precision, Recall, F1, Accuracy
    2. Decided-only (判定確定分のみ): LLMが true/false を明示した項目の中での Precision, Recall, F1, Accuracy, および Coverage (決定率 = 1 - null率)
    """
    total = len(items)
    pos_total = sum(1 for x in items if x["ground_truth"] is True)
    neg_total = sum(1 for x in items if x["ground_truth"] is False)

    tp = fp = tn = fn = null_pos = null_neg = 0
    for x in items:
        gt = x["ground_truth"]
        pred = x.get(pred_key, {}).get("is_target")
        if gt is True:
            if pred is True:
                tp += 1
            elif pred is False:
                fn += 1
            else:
                null_pos += 1
        else:
            if pred is True:
                fp += 1
            elif pred is False:
                tn += 1
            else:
                null_neg += 1

    null_total = null_pos + null_neg
    decided_total = total - null_total
    coverage = decided_total / total if total else 0.0

    # Strict metrics (where only explicit True is accepted, explicit False is rejected, and null is unaccepted/unrejected)
    # Strict Accuracy: (TP + TN) / Total
    strict_acc = (tp + tn) / total if total else 0.0
    # Precision among predicted True: TP / (TP + FP)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    # Strict Recall among all Positives: TP / Pos_Total
    strict_recall = tp / pos_total if pos_total > 0 else 0.0
    strict_f1 = (
        2 * precision * strict_recall / (precision + strict_recall)
        if (precision + strict_recall) > 0
        else 0.0
    )
    # Strict Specificity (True Negative Rate): TN / Neg_Total
    strict_tnr = tn / neg_total if neg_total > 0 else 0.0

    # Decided-only metrics (excluding nulls)
    decided_acc = (tp + tn) / decided_total if decided_total > 0 else 0.0
    decided_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    decided_f1 = (
        2 * precision * decided_recall / (precision + decided_recall)
        if (precision + decided_recall) > 0
        else 0.0
    )

    return {
        "total": total,
        "pos_total": pos_total,
        "neg_total": neg_total,
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "null_pos": null_pos,
        "null_neg": null_neg,
        "null_total": null_total,
        "null_rate": round(null_total / total * 100, 2) if total else 0.0,
        "coverage_rate": round(coverage * 100, 2),
        "strict_accuracy": round(strict_acc * 100, 2),
        "precision": round(precision * 100, 2),
        "strict_recall": round(strict_recall * 100, 2),
        "strict_f1": round(strict_f1 * 100, 2),
        "strict_tnr": round(strict_tnr * 100, 2),
        "decided_accuracy": round(decided_acc * 100, 2),
        "decided_recall": round(decided_recall * 100, 2),
        "decided_f1": round(decided_f1 * 100, 2),
    }


def run_ablation_inference(
    items: list,
    provider: str = "lmstudio",
    api_base: str = "http://localhost:1234/v1",
    api_key: str = "",
    model: str = "google/gemma-4-e4b",
    domain_definition: str = "日本の伝統音楽・古典籍における楽譜資料（雅楽・声明・邦楽・三味線・箏・尺八・琵琶・工工四・節博士等。単なる研究書・歴史書・目録や、系譜・年譜・画譜・書譜・硯譜・介譜等の非音楽資料は除外）",
    max_workers: int = 2,
) -> list:
    conditions = ["no_context", "unrestricted_web", "jp_filtered_web"]

    for cond in conditions:
        pred_key = f"pred_{cond}"
        pending_indices = [
            i for i, x in enumerate(items)
            if pred_key not in x or "API" in str(x[pred_key].get("reason", ""))
        ]
        print(f"\n=== Running Condition: {cond} ({len(pending_indices)} items to judge) ===")
        if not pending_indices:
            continue

        def judge_one(idx):
            item = items[idx]
            sys_p, usr_p = build_prompts(item, cond, domain_definition)
            t0 = time.time()
            res = _classify_single_item(
                system_prompt=sys_p,
                user_prompt=usr_p,
                provider=provider,
                api_base=api_base,
                api_key=api_key,
                model=model,
            )
            elapsed = round(time.time() - t0, 2)
            res["elapsed_sec"] = elapsed
            return idx, res

        done_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(judge_one, idx): idx for idx in pending_indices}
            for fut in as_completed(futs):
                idx, res = fut.result()
                items[idx][pred_key] = res
                done_count += 1
                if done_count % 10 == 0 or done_count == len(pending_indices):
                    print(
                        f"  [{cond}] {done_count}/{len(pending_indices)} | "
                        f"last={items[idx]['title'][:20]} -> {res.get('is_target')}"
                    )
                if done_count % 25 == 0:
                    with open(BENCHMARK_DATASET_PATH, "w", encoding="utf-8") as f:
                        for r in items:
                            f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # 各Condition終了時に保存
        with open(BENCHMARK_DATASET_PATH, "w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return items


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true", help="データセット構築とWebスニペット取得のみ実行")
    parser.add_argument("--provider", default="lmstudio")
    parser.add_argument("--api-base", default="http://localhost:1234/v1")
    parser.add_argument("--model", default="google/gemma-4-e4b")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    print("Step 1: Building 200-item benchmark dataset...")
    b_items = build_benchmark_200(seed=42)
    print(f"Total benchmark items: {len(b_items)}")
    cat_counts = Counter(x["category"] for x in b_items)
    for k, v in sorted(cat_counts.items()):
        print(f"  - {k}: {v}")

    print("\nStep 2: Fetching & caching Web context snippets (Unrestricted vs JP-Filtered)...")
    b_items = enrich_contexts_for_benchmark(b_items, max_workers=6)

    # コンテキスト取得統計の表示
    ext_hits = sum(1 for x in b_items if x.get("has_ext_url_snippet"))
    ddg_unres_hits = sum(1 for x in b_items if x.get("has_ddg_unrestricted"))
    ddg_jp_hits = sum(1 for x in b_items if x.get("has_ddg_jp_filtered"))
    wiki_hits = sum(1 for x in b_items if x.get("has_wikipedia_jp"))
    non_jp_contaminated = sum(1 for x in b_items if x.get("non_jp_lines_in_cond2", 0) > 0)
    print("\n=== Context Retrieval Statistics (200 items) ===")
    print(f"  - External Archive URL Snippets: {ext_hits}/200 ({ext_hits/2:.1f}%)")
    print(f"  - DDG Unrestricted Hits (Cond 2): {ddg_unres_hits}/200 ({ddg_unres_hits/2:.1f}%)")
    print(f"  - Items with Non-JP/Spam Contamination in Cond 2: {non_jp_contaminated}/200 ({non_jp_contaminated/2:.1f}%)")
    print(f"  - DDG JP-Filtered Hits (Cond 3): {ddg_jp_hits}/200 ({ddg_jp_hits/2:.1f}%)")
    print(f"  - Wikipedia Fallback Hits (Cond 3): {wiki_hits}/200 ({wiki_hits/2:.1f}%)")

    if not args.prepare_only:
        print("\nStep 3: Running 3-Condition LLM Ablation Inference...")
        b_items = run_ablation_inference(
            b_items,
            provider=args.provider,
            api_base=args.api_base,
            model=args.model,
            max_workers=args.workers,
        )
        summary = {}
        for cond in ["no_context", "unrestricted_web", "jp_filtered_web"]:
            summary[cond] = compute_metrics(b_items, f"pred_{cond}")
            print(f"\nMetrics [{cond}]:", json.dumps(summary[cond], ensure_ascii=False))
        with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        from generate_ablation_report import generate_full_report
        generate_full_report()

