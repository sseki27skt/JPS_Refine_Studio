# -*- coding: utf-8 -*-
"""
Japan Search メタデータ自動取得パイプライン ＆ 高速LLMサジェストの総合テスト
"""

import os
import sys
import json
import time
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "modules")))

from llm_query_expander import expand_query_with_llm, generate_sparql_queries
from sparql_collector import fetch_uris_with_query_func, build_metadata_for_uris
from rule_filter import (
    suggest_ng_keywords_with_llm,
    suggest_related_keywords_by_base,
    extract_about_values,
    extract_about_keywords_from_jsonl,
    run_about_filter
)
from ngram_filter import extract_ngrams_from_jsonl, run_ngram_filter
from review_portal import load_merged_review_data, save_human_verified_data
from llm_classifier import _parse_json_response


def test_fast_llm_suggestions():
    print("\n=== [Test 1] Fast LLM Context Suggestion Test ===")
    dummy_ng_list = [f"ダミー除外語_{i}" for i in range(500)]  # 500件の大規模リスト
    sample_kws = ["歴史", "写真", "絵画", "浄瑠璃", "雅楽", "能楽", "三味線", "地図", "軍記", "書誌"]
    target_kws = ["楽譜", "音楽", "音譜", "能楽"]

    start_time = time.time()
    suggs = suggest_ng_keywords_with_llm(
        current_ng_list=dummy_ng_list,
        sample_keywords=sample_kws,
        target_keywords=target_kws,
        domain_definition="日本の古典籍楽譜"
    )
    elapsed = time.time() - start_time
    print(f"[OK] Fast Suggestion Response Time: {elapsed:.2f} 秒")
    print(f"[OK] Returned Suggestions ({len(suggs)} items): {suggs}")
    assert elapsed < 15.0, "Response took longer than 15 seconds!"

    start_time2 = time.time()
    related_suggs = suggest_related_keywords_by_base("浄瑠璃", mode="ok", sample_keywords=sample_kws)
    elapsed2 = time.time() - start_time2
    print(f"[OK] Contextual Base Suggestion Response Time: {elapsed2:.2f} 秒")
    print(f"[OK] Related OK Suggestions for '浄瑠璃': {related_suggs}")


def test_llm_query_expansion():
    print("\n=== [Test 2] LLM Query Expansion Test ===")
    theme = "日本の古典籍における楽譜資料"
    res = expand_query_with_llm(theme)
    assert isinstance(res, dict), "Result is not dict"
    assert "theme" in res, "No theme field"
    assert "keywords" in res, "No keywords field"
    print(f"[OK] Theme: {res.get('theme')}")
    print(f"[OK] Keywords: {res.get('keywords')}")
    return res


def test_sparql_query_generation(expansion_res):
    print("\n=== [Test 3] SPARQL Query Generation Test ===")
    queries = generate_sparql_queries(expansion_res, limit=20)
    assert len(queries) > 0, "No queries generated"
    print(f"[OK] Generated {len(queries)} query patterns.")
    return queries


def test_about_extraction_and_filter():
    print("\n=== [Test 4] Schema:About Extraction & Filter Test ===")
    # Dict, List of Dict, URL str など多様な構造のテスト
    test_about_sample = [
        "http://jla.or.jp/data/ndc#760",
        {"rdfs:label": "雅楽", "@id": "http://example.org/gagaku"},
        {"schema:name": "日本音楽"},
        "地図"
    ]
    extracted = extract_about_values(test_about_sample)
    print(f"[OK] Extracted about values: {extracted}")
    assert any("760" in x for x in extracted)
    assert "雅楽" in extracted
    assert "日本音楽" in extracted
    assert "地図" in extracted

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_jsonl = os.path.join(tmpdir, "raw.jsonl")
        rules_json = os.path.join(tmpdir, "rules.json")
        out_filtered = os.path.join(tmpdir, "out.jsonl")
        out_disc = os.path.join(tmpdir, "disc.csv")

        sample_items = [
            {"@id": "item1", "rdfs:label": "雅楽の楽譜", "schema:about": [
                "http://jla.or.jp/data/ndc#760",
                {"rdfs:label": "雅楽", "@id": "http://example.org/gagaku"},
                {"schema:name": "日本音楽"}
            ]},
            {"@id": "item2", "rdfs:label": "江戸の古地図", "schema:about": ["地図", "地理"]}
        ]
        with open(raw_jsonl, 'w', encoding='utf-8') as f:
            for item in sample_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        with open(rules_json, 'w', encoding='utf-8') as f:
            json.dump({"地図": "NG", "雅楽": "OK"}, f)

        kw_counts = extract_about_keywords_from_jsonl(raw_jsonl)
        assert len(kw_counts) > 0, "No keywords extracted"

        passed, disc = run_about_filter(raw_jsonl, rules_json, out_filtered, out_disc)
        print(f"[OK] About Filter: passed={passed}, disc={disc}")
        assert passed == 1
        assert disc == 1


def test_ngram_extraction_and_filter():
    print("\n=== [Test 5] N-Gram Extraction & Filter Test ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_jsonl = os.path.join(tmpdir, "raw.jsonl")
        rules_json = os.path.join(tmpdir, "rules.json")
        out_filtered = os.path.join(tmpdir, "out.jsonl")
        out_disc = os.path.join(tmpdir, "disc.csv")

        sample_items = [
            {"@id": "item1", "rdfs:label": "新選楽譜集 第1巻"},
            {"@id": "item2", "rdfs:label": "徳川家系譜図"},
            {"@id": "item3", "rdfs:label": "新選楽譜集 第2巻"}
        ]
        with open(raw_jsonl, 'w', encoding='utf-8') as f:
            for item in sample_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        ngrams = extract_ngrams_from_jsonl(raw_jsonl, min_n=2, max_n=3)
        assert 2 in ngrams
        print(f"[OK] Extracted Bi-gram top items count: {len(ngrams[2])}")

        with open(rules_json, 'w', encoding='utf-8') as f:
            json.dump({"系譜": "NG"}, f)

        passed, disc = run_ngram_filter(raw_jsonl, rules_json, out_filtered, out_disc)
        print(f"[OK] N-Gram Filter: passed={passed}, disc={disc}")
        assert passed == 2
        assert disc == 1


def test_review_portal_and_classifier_parser():
    print("\n=== [Test 6] Review Portal & LLM Response Parser Test ===")
    # JSON レスポンスパースのテスティング (Markdown backticks, JSON)
    markdown_json = "```json\n{\"is_target\": true, \"reason\": \"楽譜資料と判定\"}\n```"
    parsed = _parse_json_response(markdown_json)
    assert parsed.get("is_target") is True
    assert parsed.get("reason") == "楽譜資料と判定"
    print(f"[OK] LLM Classifier JSON Parser test passed.")

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_jsonl = os.path.join(tmpdir, "raw.jsonl")
        about_filtered = os.path.join(tmpdir, "about.jsonl")
        verified_out = os.path.join(tmpdir, "verified.jsonl")

        sample_item = {"@id": "item1", "rdfs:label": "雅楽楽譜"}
        with open(raw_jsonl, 'w', encoding='utf-8') as f:
            f.write(json.dumps(sample_item) + "\n")
        with open(about_filtered, 'w', encoding='utf-8') as f:
            f.write(json.dumps(sample_item) + "\n")

        # suffix_filtered_path が None の場合でも例外が起きないかチェック
        records = load_merged_review_data(
            raw_jsonl_path=raw_jsonl,
            about_filtered_path=about_filtered,
            suffix_filtered_path=None,
            ngram_filtered_path=None,
            llm_judgments_path=None
        )
        assert len(records) == 1
        assert records[0]["status"] == "合格"
        print(f"[OK] Review portal merged data loaded cleanly without TypeError.")

        saved_cnt = save_human_verified_data(records, {"item1": "合格"}, verified_out)
        assert saved_cnt == 1
        print(f"[OK] Saved human verified records count: {saved_cnt}")


def test_symbol_cleaning_and_multithreaded_classifier():
    print("\n=== [Test 7] Symbol Cleaning & Multithreaded LLM Classifier Test ===")
    from llm_classifier import run_llm_semantic_classification

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_jsonl = os.path.join(tmpdir, "raw.jsonl")
        out_judgments = os.path.join(tmpdir, "llm_out.jsonl")

        sample_items = [
            {"@id": "item1", "rdfs:label": "雅楽・古典楽譜 (第1巻)", "schema:description": "雅楽の楽譜です。"},
            {"@id": "item2", "rdfs:label": "【徳川】家系図！―全集―", "schema:description": "系図資料です。"},
            {"@id": "item3", "rdfs:label": "《謡曲》観世流「譜」〜完全版〜", "schema:description": "謡本の譜面です。"}
        ]
        with open(raw_jsonl, 'w', encoding='utf-8') as f:
            for item in sample_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # N-Gram 記号除去テスト
        ngrams = extract_ngrams_from_jsonl(raw_jsonl, min_n=2, max_n=3)
        assert 2 in ngrams
        bi_gram_words = [w for w, c, s in ngrams[2]]
        # 記号 (・, ( ), 【 】, ！, ―, 《 》, 「 」, 〜) が除去されていること
        for word in bi_gram_words:
            assert not any(symbol in word for symbol in ["・", "(", "【", "！", "―", "《", "「", "〜"])
        print(f"[OK] Clean symbol N-Gram extraction verified. Bi-grams: {bi_gram_words}")

        # 並列LLM分類テスト (provider='local', max_workers=2)
        acc, rej, unk = run_llm_semantic_classification(
            input_jsonl_path=raw_jsonl,
            output_judgments_path=out_judgments,
            domain_definition="古典楽譜資料",
            provider="local",
            limit=3,
            max_workers=2
        )
        assert os.path.exists(out_judgments)
        print(f"[OK] Multithreaded LLM classifier finished successfully. (acc={acc}, rej={rej}, unk={unk})")


if __name__ == "__main__":
    print("--------------------------------------------------")
    print("  Japan Search Enhanced Pipeline & Module Unit Tests")
    print("--------------------------------------------------")
    try:
        test_fast_llm_suggestions()
        exp_res = test_llm_query_expansion()
        queries = test_sparql_query_generation(exp_res)
        test_about_extraction_and_filter()
        test_ngram_extraction_and_filter()
        test_review_portal_and_classifier_parser()
        test_symbol_cleaning_and_multithreaded_classifier()
        print("\n==================================================")
        print(" SUCCESS: All enhanced pipeline & module tests passed!")
        print("==================================================")
    except Exception as e:
        print(f"\n[FAIL] Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


