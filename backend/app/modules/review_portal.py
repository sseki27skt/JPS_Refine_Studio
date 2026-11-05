# -*- coding: utf-8 -*-
"""
JS-Refine Studio - 専門家による最終査読・手動オーバーライドポータル モジュール
"""

import json
import os
import pandas as pd


def load_merged_review_data(
    raw_jsonl_path: str,
    about_filtered_path: str = None,
    type_filtered_path: str = None,
    ngram_filtered_path: str = None,
    suffix_filtered_path: str = None,
    llm_judgments_path: str = None
) -> list:
    """
    全工程（Type, About, N-Gram, LLM判定）の結果を集約し、
    各資料の現在の判定ステータスと判定理由バッジが付与された統合査読データを返します。
    """
    if not os.path.exists(raw_jsonl_path):
        return []

    # 各フェーズの合格ID集合を作成
    type_passed_ids = set()
    if type_filtered_path and os.path.exists(type_filtered_path):
        with open(type_filtered_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        type_passed_ids.add(item.get("@id", item.get("id", "")))
                    except Exception:
                        pass

    about_passed_ids = set()
    if about_filtered_path and os.path.exists(about_filtered_path):
        with open(about_filtered_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        about_passed_ids.add(item.get("@id", item.get("id", "")))
                    except Exception:
                        pass

    ngram_passed_ids = set()
    if ngram_filtered_path and os.path.exists(ngram_filtered_path):
        with open(ngram_filtered_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        ngram_passed_ids.add(item.get("@id", item.get("id", "")))
                    except Exception:
                        pass

    # LLM判定結果のマップ
    llm_map = {}
    if llm_judgments_path and os.path.exists(llm_judgments_path):
        with open(llm_judgments_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip():
                    try:
                        j = json.loads(line)
                        llm_map[j.get("id", "")] = j
                    except Exception:
                        pass

    merged_records = []

    with open(raw_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue

            item_id = item.get("@id", item.get("id", ""))
            label = item.get("rdfs:label", item.get("schema:name", "No Title"))
            title = label[0] if isinstance(label, list) and label else str(label)

            # 各フェーズでの判定ステータス評価
            is_type_ok = item_id in type_passed_ids if type_passed_ids else True
            is_about_ok = item_id in about_passed_ids if about_passed_ids else True
            is_ngram_ok = item_id in ngram_passed_ids if ngram_passed_ids else True
            
            llm_info = llm_map.get(item_id, {})
            llm_target = llm_info.get("is_target")
            llm_reason = llm_info.get("reason", "")
            external_info = llm_info.get("external_info", "")

            # 総合初期判定
            final_status = "合格"
            reasons = []

            if not is_type_ok:
                final_status = "除外"
                reasons.append("データ種別(Type)除外")
            if not is_about_ok:
                final_status = "除外"
                reasons.append("Aboutルール除外")
            if not is_ngram_ok:
                final_status = "除外"
                reasons.append("タイトルルール除外")

            if llm_target is False:
                final_status = "除外"
                reasons.append(f"LLM判定除外: {llm_reason}")
            elif llm_target is True:
                if "[ルール合格]" in llm_reason:
                    reasons.append(f"ルール判定適合 (LLMバイパス): {llm_reason}")
                else:
                    reasons.append(f"LLM判定適合: {llm_reason}")
            elif llm_target is None and "LLM" in str(llm_info.get("source_stage", "")):
                reasons.append(f"LLM判定不能 (null): {llm_reason}")

            if not reasons:
                reasons.append("全ルール通過")

            merged_records.append({
                "id": item_id,
                "title": title,
                "status": final_status,
                "reasons": " / ".join(reasons),
                "is_type_ok": is_type_ok,
                "is_about_ok": is_about_ok,
                "is_ngram_ok": is_ngram_ok,
                "llm_target": llm_target,
                "llm_reason": llm_reason,
                "external_info": external_info,
                "raw_item": item
            })

    return merged_records


def save_human_verified_data(records: list, human_decisions: dict, output_verified_jsonl: str) -> int:
    """
    人間が手動オーバーライド修正を行った最終確定データを jsonl へ保存します。
    human_decisions: {item_id: "合格" または "除外"}
    """
    os.makedirs(os.path.dirname(output_verified_jsonl), exist_ok=True)

    passed_count = 0
    with open(output_verified_jsonl, 'w', encoding='utf-8') as f:
        for r in records:
            item_id = r["id"]
            human_status = human_decisions.get(item_id, r["status"])
            
            if human_status == "合格":
                raw_item = r["raw_item"]
                raw_item["human_verified_status"] = "APPROVED"
                raw_item["review_reasons"] = r["reasons"]
                f.write(json.dumps(raw_item, ensure_ascii=False) + "\n")
                passed_count += 1

    return passed_count
