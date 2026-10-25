# -*- coding: utf-8 -*-
"""
タイトル N-Gram (N=2〜9) マイニング ＆ ルールフィルタリングモジュール
"""

import json
import os
import re
import pandas as pd
from collections import Counter, defaultdict


def clean_title_text(title: str) -> str:
    """
    タイトルから記号・数字・括弧類・約物を網羅的に除去して標準化テキストを返します。
    """
    if not title:
        return ""
    return re.sub(r'[\s　\(\)（）\[\]【】「」『』\.,:：［］;!\?/\-_\d・―〜〈〉《》“”‘’\+=★☆◆◇▲△▼▽○●◎／\[\]〔〕、；]', '', title)


def extract_ngrams_from_jsonl(input_jsonl_path: str, min_n: int = 2, max_n: int = 9, top_n_per_gram: int = 500) -> dict:
    """
    jsonl ファイル内の資料タイトルから N-gram (N=2〜9) を集計し、
    {
      2: [(word, count, [sample1, sample2]), ...],
      3: [...],
      ...
      9: [...]
    }
    の辞書形式で返します。
    """
    if not os.path.exists(input_jsonl_path):
        return {n: [] for n in range(min_n, max_n + 1)}

    counts = {n: Counter() for n in range(min_n, max_n + 1)}
    samples = {n: defaultdict(list) for n in range(min_n, max_n + 1)}

    with open(input_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                label_val = item.get("rdfs:label", item.get("schema:name", ""))
                if isinstance(label_val, list) and label_val:
                    title = str(label_val[0]).strip()
                else:
                    title = str(label_val).strip()

                if not title:
                    continue

                # 記号・数字・括弧類・約物を網羅的に除去
                clean_title = clean_title_text(title)

                for n in range(min_n, max_n + 1):
                    if len(clean_title) >= n:
                        ngrams = [clean_title[i:i+n] for i in range(len(clean_title) - n + 1)]
                        for word in set(ngrams):
                            counts[n][word] += 1
                            if len(samples[n][word]) < 30 and title not in samples[n][word]:
                                samples[n][word].append(title)
            except Exception:
                continue

    result_dict = {}
    for n in range(min_n, max_n + 1):
        ranking = []
        for word, count in counts[n].most_common(top_n_per_gram):
            if count >= 2:  # 出現回数2回以上を抽出
                ranking.append((word, count, samples[n][word]))
        result_dict[n] = ranking

    return result_dict


def run_ngram_filter(input_jsonl_path: str, rules_json_path: str, output_filtered_path: str, output_discarded_csv: str):
    """タイトル N-Gram ルールに基づいてデータをフィルタリング"""
    if not os.path.exists(input_jsonl_path):
        return 0, 0

    ngram_rules = {}
    if os.path.exists(rules_json_path):
        with open(rules_json_path, 'r', encoding='utf-8') as f:
            ngram_rules = json.load(f)

    ng_patterns = set([pattern for pattern, status in ngram_rules.items() if status == "NG"])

    passed_count = 0
    discarded_records = []

    os.makedirs(os.path.dirname(output_filtered_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_discarded_csv), exist_ok=True)

    with open(input_jsonl_path, 'r', encoding='utf-8') as in_f, \
         open(output_filtered_path, 'w', encoding='utf-8') as out_f:

        for line in in_f:
            if not line.strip():
                continue
            item = json.loads(line)
            
            label_val = item.get("rdfs:label", item.get("schema:name", ""))
            if isinstance(label_val, list) and label_val:
                title_str = str(label_val[0])
            else:
                title_str = str(label_val)

            has_ng = False
            matched_pattern = ""
            for pattern in ng_patterns:
                if pattern in title_str:
                    has_ng = True
                    matched_pattern = pattern
                    break

            if has_ng:
                discarded_records.append({
                    "id": item.get("@id", ""),
                    "title": title_str,
                    "matched_pattern": matched_pattern,
                    "reason": f"N-Gramルール除外: 「{matched_pattern}」"
                })
            else:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                passed_count += 1

    if discarded_records:
        df_disc = pd.DataFrame(discarded_records)
        df_disc.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    return passed_count, len(discarded_records)
