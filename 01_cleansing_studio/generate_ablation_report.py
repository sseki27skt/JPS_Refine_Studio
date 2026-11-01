# -*- coding: utf-8 -*-
"""
LLMコンテキスト拡張アブレーション実験の詳細集計・レポート生成スクリプト
"""

import csv
import json
import os
from collections import Counter, defaultdict
from evaluate_llm_context import (
    BENCHMARK_DATASET_PATH,
    BENCHMARK_DIR,
    REPORT_MD_PATH,
    RESULTS_CSV_PATH,
    RESULTS_JSON_PATH,
    compute_metrics,
)


def generate_full_report():
    if not os.path.exists(BENCHMARK_DATASET_PATH):
        print(f"File not found: {BENCHMARK_DATASET_PATH}")
        return

    items = []
    with open(BENCHMARK_DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    conditions = [
        ("no_context", "① コンテキスト拡張なし"),
        ("unrestricted_web", "② Web拡張（日本語縛りなし）"),
        ("jp_filtered_web", "③ Web拡張（日本語縛りあり・本番環境）"),
    ]

    overall_summary = {}
    for cond_key, cond_label in conditions:
        overall_summary[cond_key] = compute_metrics(items, f"pred_{cond_key}")

    # サブカテゴリ別集計
    categories = sorted(list({x["category"] for x in items}))
    category_summary = {}
    for cat in categories:
        sub_items = [x for x in items if x["category"] == cat]
        category_summary[cat] = {}
        for cond_key, _ in conditions:
            category_summary[cat][cond_key] = compute_metrics(sub_items, f"pred_{cond_key}")

    # 情報源ヒット率集計
    total_n = len(items)
    ext_hits = sum(1 for x in items if x.get("has_ext_url_snippet"))
    ddg_unres_hits = sum(1 for x in items if x.get("has_ddg_unrestricted"))
    ddg_jp_hits = sum(1 for x in items if x.get("has_ddg_jp_filtered"))
    wiki_hits = sum(1 for x in items if x.get("has_wikipedia_jp"))
    any_cond3_hits = sum(
        1 for x in items if x.get("context_jp_filtered", "補足情報なし") != "補足情報なし"
    )
    non_jp_contaminated = sum(1 for x in items if x.get("non_jp_lines_in_cond2", 0) > 0)

    # ケーススタディ抽出
    # Case A: ①でnullまたは誤判定 -> ③で正解に改善した例
    improved_1_to_3 = []
    # Case B: ②（日本語縛りなし）で海外ノイズ等により誤判定/null -> ③（日本語縛りあり）で正解に改善した例
    improved_2_to_3 = []

    for x in items:
        gt = x["ground_truth"]
        p1 = x.get("pred_no_context", {}).get("is_target")
        p2 = x.get("pred_unrestricted_web", {}).get("is_target")
        p3 = x.get("pred_jp_filtered_web", {}).get("is_target")

        if p1 != gt and p3 == gt:
            improved_1_to_3.append(x)
        if p2 != gt and p3 == gt:
            improved_2_to_3.append(x)

    # JSON保存
    full_stats = {
        "overall": overall_summary,
        "by_category": category_summary,
        "context_retrieval": {
            "total": total_n,
            "ext_url_hits": ext_hits,
            "ddg_unrestricted_hits": ddg_unres_hits,
            "ddg_jp_filtered_hits": ddg_jp_hits,
            "wikipedia_jp_hits": wiki_hits,
            "any_cond3_context_hits": any_cond3_hits,
            "non_jp_contaminated_in_cond2": non_jp_contaminated,
        },
        "improved_1_to_3_count": len(improved_1_to_3),
        "improved_2_to_3_count": len(improved_2_to_3),
    }
    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(full_stats, f, ensure_ascii=False, indent=2)

    # 詳細CSV保存
    with open(RESULTS_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id",
            "title",
            "ground_truth",
            "category",
            "has_fu_in_title",
            "non_jp_lines_in_cond2",
            "pred_1_no_context",
            "reason_1_no_context",
            "pred_2_unrestricted",
            "reason_2_unrestricted",
            "pred_3_jp_filtered",
            "reason_3_jp_filtered",
        ])
        for x in items:
            writer.writerow([
                x["id"],
                x["title"],
                x["ground_truth"],
                x["category"],
                x["has_fu_in_title"],
                x.get("non_jp_lines_in_cond2", 0),
                x.get("pred_no_context", {}).get("is_target"),
                x.get("pred_no_context", {}).get("reason", ""),
                x.get("pred_unrestricted_web", {}).get("is_target"),
                x.get("pred_unrestricted_web", {}).get("reason", ""),
                x.get("pred_jp_filtered_web", {}).get("is_target"),
                x.get("pred_jp_filtered_web", {}).get("reason", ""),
            ])

    # Markdownレポート作成
    lines = []
    lines.append("# LLMコンテキスト拡張の効果測定・アブレーション実験レポート")
    lines.append("")
    lines.append("## 1. 実験設定")
    lines.append("- **使用モデル**: `google/gemma-4-E4B-it` (`google/gemma-4-e4b` on LM Studio, `temperature=0.0`)")
    lines.append("- **評価データセット**: 合計 200件（正例 100件 / 負例 100件）")
    lines.append("  - **正例（100件）**: `scores.jsonl` のうち、前段ルールで「判定保留（グレーゾーン）」となった資料を正規化タイトルで名寄せ（720ユニークタイトル）し、無作為抽出した100件（タイトルに「譜」を含むもの16件、「譜」を含まない隠れ楽譜資料84件）。")
    lines.append("  - **負例（100件）**: 既存ワークスペースから抽出した紛らわしい非楽譜資料100件（①系譜・年譜・世譜 25件、②画譜・書譜・印譜・紋譜 25件、③硯譜・介譜・花譜等の博物・趣味譜 25件、④音楽研究書・解説書・楽器実物等の境界ノイズ 25件）。")
    lines.append("")
    lines.append("## 2. 全体評価結果（3条件比較）")
    lines.append("")
    lines.append("### 表1: システム全体としての判定性能（Strict評価：`null` 保留を未解決として母数に含む）")
    lines.append("| 実験条件 | 正解率 (Strict Acc.) | 適合率 (Precision) | 再現率 (Strict Recall) | 特異度・棄却率 (TNR) | F1スコア (Strict F1) | 判定保留率 (`null`率) | 決定率 (Coverage) |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for cond_key, cond_label in conditions:
        m = overall_summary[cond_key]
        lines.append(
            f"| **{cond_label}** | **{m['strict_accuracy']:.1f}%** | **{m['precision']:.1f}%** | "
            f"**{m['strict_recall']:.1f}%** | **{m['strict_tnr']:.1f}%** | **{m['strict_f1']:.1f}%** | "
            f"{m['null_rate']:.1f}% ({m['null_total']}件) | {m['coverage_rate']:.1f}% |"
        )

    lines.append("")
    lines.append("### 表2: 混同行列の内訳（正例100件・負例100件）")
    lines.append("| 実験条件 | TP (正例→True) | FN (正例→False) | 正例保留 (正例→null) | TN (負例→False) | FP (負例→True) | 負例保留 (負例→null) | 判定確定分の正解率 (Decided Acc.) |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for cond_key, cond_label in conditions:
        m = overall_summary[cond_key]
        lines.append(
            f"| **{cond_label}** | {m['TP']} | {m['FN']} | {m['null_pos']} | "
            f"{m['TN']} | {m['FP']} | {m['null_neg']} | **{m['decided_accuracy']:.1f}%** |"
        )

    lines.append("")
    lines.append("## 3. サブカテゴリ別（層別）詳細分析")
    lines.append("")
    lines.append("| カテゴリ (件数) | ① 拡張なし 正解数 (保留数) | ② 日本語縛りなし 正解数 (保留数) | ③ 日本語縛りあり 正解数 (保留数) | ①→③ 改善幅 |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for cat in categories:
        m1 = category_summary[cat]["no_context"]
        m2 = category_summary[cat]["unrestricted_web"]
        m3 = category_summary[cat]["jp_filtered_web"]
        n_cat = m1["total"]
        c1 = m1["TP"] if cat.startswith("POS") else m1["TN"]
        c2 = m2["TP"] if cat.startswith("POS") else m2["TN"]
        c3 = m3["TP"] if cat.startswith("POS") else m3["TN"]
        diff = c3 - c1
        sign = "+" if diff >= 0 else ""
        lines.append(
            f"| **{cat}** ({n_cat}件) | {c1}/{n_cat} ({m1['strict_accuracy']:.1f}%, null:{m1['null_total']}) | "
            f"{c2}/{n_cat} ({m2['strict_accuracy']:.1f}%, null:{m2['null_total']}) | "
            f"**{c3}/{n_cat} ({m3['strict_accuracy']:.1f}%, null:{m3['null_total']})** | **{sign}{diff}件 ({sign}{m3['strict_accuracy']-m1['strict_accuracy']:.1f}pt)** |"
        )

    lines.append("")
    lines.append("## 4. コンテキスト取得源と海外ノイズ混入の統計")
    lines.append(f"- **原典アーカイブ（外部URL）からのスニペット取得成功**: {ext_hits}/200件 ({ext_hits/2:.1f}%)")
    lines.append(f"- **条件②（日本語縛りなしDDG検索）ヒット数**: {ddg_unres_hits}/200件 ({ddg_unres_hits/2:.1f}%)")
    lines.append(f"  - うち**非日本語（中国語・英語・海外掲示板スパム等）が混入した資料数**: **{non_jp_contaminated}/200件 ({non_jp_contaminated/2:.1f}%)**")
    lines.append(f"- **条件③（日本語縛りありDDG検索）ヒット数**: {ddg_jp_hits}/200件 ({ddg_jp_hits/2:.1f}%)")
    lines.append(f"- **条件③ Wikipedia API フォールバックヒット数**: {wiki_hits}/200件 ({wiki_hits/2:.1f}%)")
    lines.append(f"- **条件③ 最終的に有効な補足情報が得られた資料数**: **{any_cond3_hits}/200件 ({any_cond3_hits/2:.1f}%)**")
    lines.append("")
    lines.append("## 5. 代表的な改善ケーススタディ")
    lines.append(f"- **①拡張なし → ③本番環境で改善した資料**: 計 **{len(improved_1_to_3)}件**")
    for x in improved_1_to_3[:8]:
        p1 = x.get("pred_no_context", {})
        p3 = x.get("pred_jp_filtered_web", {})
        lines.append(
            f"  - **`{x['title']}`** ({x['category']}, 正解=`{x['ground_truth']}`): "
            f"① `{p1.get('is_target')}` ({p1.get('reason', '')[:50]}...) → "
            f"③ **`{p3.get('is_target')}`** ({p3.get('reason', '')[:60]}...)"
        )

    lines.append(f"- **②日本語縛りなし → ③日本語縛りありで改善した資料**: 計 **{len(improved_2_to_3)}件**")
    for x in improved_2_to_3[:8]:
        p2 = x.get("pred_unrestricted_web", {})
        p3 = x.get("pred_jp_filtered_web", {})
        lines.append(
            f"  - **`{x['title']}`** ({x['category']}, 正解=`{x['ground_truth']}`, 非日本語混入={x.get('non_jp_lines_in_cond2', 0)}行): "
            f"② `{p2.get('is_target')}` ({p2.get('reason', '')[:50]}...) → "
            f"③ **`{p3.get('is_target')}`** ({p3.get('reason', '')[:60]}...)"
        )

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Generated full report at: {REPORT_MD_PATH}")


if __name__ == "__main__":
    generate_full_report()

