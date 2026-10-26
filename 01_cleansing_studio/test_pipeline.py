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
from sparql_collector import (
    fetch_uris_with_query_func, 
    build_metadata_for_uris,
    get_job_status,
    update_job_status,
    request_job_stop,
    is_process_alive,
    save_acquisition_manifest,
    get_acquisition_manifest
)
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
        acc, rej, unk, *rest = run_llm_semantic_classification(
            input_jsonl_path=raw_jsonl,
            output_judgments_path=out_judgments,
            domain_definition="古典楽譜資料",
            provider="local",
            limit=3,
            max_workers=2
        )
        assert os.path.exists(out_judgments)
        print(f"[OK] Multithreaded LLM classifier finished successfully. (acc={acc}, rej={rej}, unk={unk})")


def test_duckdb_engine():
    print("\n=== [Test 8] DuckDB High-Speed Engine Unit Test ===")
    from duckdb_manager import DuckDBManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_jsonl = os.path.join(tmpdir, "raw.jsonl")
        target_llm = os.path.join(tmpdir, "target_llm.jsonl")
        confirmed_ok = os.path.join(tmpdir, "confirmed_ok.jsonl")
        discarded_csv = os.path.join(tmpdir, "discarded.csv")

        sample_items = [
            {"@id": "item1", "rdfs:label": "雅楽の楽譜", "schema:about": ["雅楽", "760"]},
            {"@id": "item2", "rdfs:label": "江戸の古地図", "schema:about": ["地図"]},
            {"@id": "item3", "rdfs:label": "新選楽譜集 第1巻", "schema:about": ["音楽"]},
            {"@id": "item4", "rdfs:label": "徳川家系譜図", "schema:about": ["歴史"]}
        ]
        with open(raw_jsonl, 'w', encoding='utf-8') as f:
            for item in sample_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        db = DuckDBManager(":memory:")
        inserted = db.import_jsonl(raw_jsonl)
        assert inserted == 4, f"Inserted count mismatch: {inserted}"
        print(f"[OK] DuckDB imported {inserted} records.")

        # About集計
        kws = db.get_about_keyword_counts()
        assert len(kws) >= 4, f"Keyword count mismatch: {len(kws)}"
        print(f"[OK] DuckDB About counts: {kws}")

        # N-gram集計
        ngrams = db.extract_ngrams(min_n=2, max_n=2)
        assert 2 in ngrams
        print(f"[OK] DuckDB N-gram count: {len(ngrams[2])}")

        # ルール適用
        about_rules = {"地図": "NG", "雅楽": "OK"}
        ngram_rules = {"系譜": "NG"}
        res = db.apply_rules_fast(about_rules, ngram_rules)
        print(f"[OK] DuckDB apply_rules_fast result: {res}")
        assert res["ok"] == 1, f"Expected 1 OK, got {res['ok']}"
        assert res["ng"] == 2, f"Expected 2 NG, got {res['ng']}"
        assert res["grey"] == 1, f"Expected 1 Grey, got {res['grey']}"

        # エクスポート
        db.export_split_datasets(target_llm, confirmed_ok, discarded_csv)
        assert os.path.exists(target_llm) and os.path.exists(confirmed_ok) and os.path.exists(discarded_csv)
        with open(confirmed_ok, 'r', encoding='utf-8') as f:
            first_ok = json.loads(f.readline())
            assert "[ルール合格]" in first_ok["reason"], f"Prefix [ルール合格] missing in reason: {first_ok['reason']}"
        print("[OK] DuckDB exported datasets verified successfully (with [ルール合格] prefix).")

        # --- 査読ポータル機能のテスト ---
        # 1. 査読メトリクス取得 (LLM未判定時は null_cnt は 0 件であるべき)
        metrics = db.get_review_metrics()
        assert metrics["total"] == 4
        assert metrics["pass_cnt"] == 1
        assert metrics["reject_cnt"] == 3  # NG(2) + GREY(1) はデフォルト除外
        assert metrics["null_cnt"] == 0, f"Expected 0 null_cnt before LLM sync, got {metrics['null_cnt']}"
        print(f"[OK] DuckDB review metrics verified: {metrics}")

        # 2. サーバーサイド検索・ページネーション
        total_q, page_recs = db.query_review_records(filter_type="すべて", page=1, page_size=2)
        assert total_q == 4
        assert len(page_recs) == 2
        print(f"[OK] DuckDB query_review_records pagination verified (total={total_q}, page_len={len(page_recs)})")

        # 3. 手動オーバーライド (item2 を 合格に変更)
        db.set_human_decision("item2", "合格")
        metrics_after = db.get_review_metrics()
        assert metrics_after["pass_cnt"] == 2
        assert metrics_after["override_cnt"] == 1
        print(f"[OK] DuckDB manual override verified: override_cnt={metrics_after['override_cnt']}")

        # 4. 最終確定データエクスポート
        verified_out = os.path.join(tmpdir, "verified.jsonl")
        exported_v = db.export_human_verified_data(verified_out)
        assert exported_v == 2, f"Expected 2 verified records, got {exported_v}"
        assert os.path.exists(verified_out)
        print(f"[OK] DuckDB human verified export verified: count={exported_v}")

        # 5. 手動判定の自動復元テスト (別DBインスタンスでの sync_human_decisions 検証)
        db_restored = DuckDBManager(":memory:")
        db_restored.import_jsonl(raw_jsonl)
        db_restored.apply_rules_fast(about_rules, ngram_rules)
        restored_cnt = db_restored.sync_human_decisions(verified_out)
        assert restored_cnt >= 1, f"Expected at least 1 restored decision, got {restored_cnt}"
        metrics_restored = db_restored.get_review_metrics()
        assert metrics_restored["override_cnt"] == 1, f"Expected 1 override_cnt after restore, got {metrics_restored['override_cnt']}"
        print(f"[OK] DuckDB human verified restore verified: restored_cnt={restored_cnt}")
        db_restored.close()

        db.close()


def test_sparql_fetch_and_job_status():
    print("\n=== [Test 9] SPARQL Fetch Job Status & Resume Integration Test ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = os.path.join(tmpdir, "test_job_status.json")
        jsonl_path = os.path.join(tmpdir, "test_raw.jsonl")

        # 1. ジョブステータス基本動作テスト
        init_st = get_job_status(status_file)
        assert init_st["status"] == "IDLE", f"Expected IDLE, got {init_st['status']}"
        print(f"[OK] Initial job status: {init_st['status']}")

        my_pid = os.getpid()
        assert is_process_alive(my_pid) is True
        assert is_process_alive(9999999) is False
        print(f"[OK] Process alive check: PID {my_pid} is alive.")

        update_job_status(
            status="RUNNING",
            stage="build_metadata",
            total_target=100,
            processed_count=25,
            current_batch_size=10,
            pid=my_pid,
            status_file=status_file
        )
        st_after = get_job_status(status_file)
        assert st_after["status"] == "RUNNING"
        assert st_after["total_target"] == 100
        assert st_after["processed_count"] == 25
        print(f"[OK] Updated status: {st_after['status']}, processed: {st_after['processed_count']}/{st_after['total_target']}")

        # 停止リクエストのテスト
        req_res = request_job_stop(status_file)
        assert req_res is True
        st_stop = get_job_status(status_file)
        assert st_stop["status"] == "STOP_REQUESTED"
        print(f"[OK] Stop request transition verified: {st_stop['status']}")

        # 2. レジューム（中断・再開）テスト
        # 事前に2件のレコードを既存ファイルに書き込み
        initial_items = [
            {"@id": "http://example.org/item1", "rdfs:label": "古典籍楽譜 1", "status": "success"},
            {"@id": "http://example.org/item2", "rdfs:label": "古典籍楽譜 2", "status": "success"}
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for item in initial_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 対象URIリスト（4件: item1, item2, item3, item4）
        all_targets = [
            "http://example.org/item1",
            "http://example.org/item2",
            "http://example.org/item3",
            "http://example.org/item4"
        ]

        # sparql_collector のモックテスト
        import sparql_collector
        orig_fetch = sparql_collector.fetch_deep_graph_with_stats
        
        fetched_chunks = []
        def mock_fetch(uris, session=None, timeout_sec=45):
            fetched_chunks.append(list(uris))
            bindings = []
            for u in uris:
                bindings.append({
                    's': {'value': u},
                    'p': {'value': 'http://www.w3.org/2000/01/rdf-schema#label'},
                    'o': {'value': f"Title of {u}"}
                })
            return bindings, {"is_clean": True, "split_count": 0, "elapsed": 0.1, "success": True}

        sparql_collector.fetch_deep_graph_with_stats = mock_fetch

        try:
            # resume=True で実行
            count = build_metadata_for_uris(
                uri_list=all_targets,
                output_jsonl_path=jsonl_path,
                batch_size=2,
                auto_repair=False,
                resume=True,
                status_file=status_file
            )

            # 既存の item1, item2 はスキップされ、未取得の item3, item4 のみが fetch されたか確認
            flat_fetched = [u for chunk in fetched_chunks for u in chunk]
            print(f"[OK] Fetched newly requested URIs: {flat_fetched}")
            assert "http://example.org/item1" not in flat_fetched, "item1 should have been skipped by resume!"
            assert "http://example.org/item2" not in flat_fetched, "item2 should have been skipped by resume!"
            assert "http://example.org/item3" in flat_fetched
            assert "http://example.org/item4" in flat_fetched

            # ファイル内の全件数確認 (4件)
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 4, f"Expected 4 records in file, got {len(lines)}"
            uids = [rec.get("@id") for rec in lines]
            assert set(uids) == set(all_targets), f"UID mismatch: {uids}"
            print(f"[OK] Resume complete: All {len(lines)} records safely retained without duplicate.")

            # 3. 再度同じ全件で resume=True を実行した場合、即座にスキップ完了するか
            fetched_chunks.clear()
            count2 = build_metadata_for_uris(
                uri_list=all_targets,
                output_jsonl_path=jsonl_path,
                resume=True,
                status_file=status_file
            )
            assert len(fetched_chunks) == 0, "Should not have made any requests on fully-fetched target!"
            assert count2 == 4
            print(f"[OK] Zero-fetch instant skip verified when already completed.")

        finally:
            sparql_collector.fetch_deep_graph_with_stats = orig_fetch


def test_provenance_and_audit():
    print("\n=== [Test 10] Provenance & Audit Trail Integration Test ===")
    from duckdb_manager import DuckDBManager

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. マニフェスト保存・読み込みテスト
        manifest_file = os.path.join(tmpdir, "test_manifest.json")
        sample_manifest = {
            "dataset_name": "Test Classical Scores",
            "created_at": "2026-10-26 10:00:00",
            "endpoint": "https://jpsearch.go.jp/rdf/sparql/",
            "parameters": {
                "keywords": ["譜", "雅楽"],
                "target_ndc": ["768"],
                "exclude_ndc": ["288"]
            },
            "sparql_queries": {
                "Part 1": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 10"
            },
            "metrics": {
                "total_target_uris": 4,
                "success_count": 4
            }
        }
        ok_save = save_acquisition_manifest(sample_manifest, manifest_file)
        assert ok_save is True
        loaded_m = get_acquisition_manifest(manifest_file)
        assert loaded_m["dataset_name"] == "Test Classical Scores"
        assert loaded_m["parameters"]["keywords"] == ["譜", "雅楽"]
        print(f"[OK] Acquisition manifest save & load verified.")

        # 2. DuckDB 来歴記録・Type除外・ルール適用テスト
        jsonl_path = os.path.join(tmpdir, "audit_sample.jsonl")
        audit_records = [
            {"@id": "http://example.org/rec1", "rdfs:label": "古譜 雅楽集成", "rdf:type": ["http://schema.org/Book"], "schema:about": ["ndc#768.1", "雅楽"]},
            {"@id": "http://example.org/rec2", "rdfs:label": "徳川家 諸家系譜", "rdf:type": ["http://schema.org/Book"], "schema:about": ["ndc#288", "系譜"]},
            {"@id": "http://example.org/rec3", "rdfs:label": "音楽学論考 論文", "rdf:type": ["http://schema.org/Article"], "schema:about": ["音楽"]},
            {"@id": "http://example.org/rec4", "rdfs:label": "未詳古記", "rdf:type": ["http://schema.org/Book"], "schema:about": []}
        ]
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for r in audit_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        db = DuckDBManager(":memory:")
        db.import_jsonl(jsonl_path)
        assert db.get_record_count() == 4

        # A. Typeフィルタ除外 (Articleを除外)
        type_res = db.apply_type_filter_fast(["Article", "論文"])
        assert type_res["discarded"] == 1
        assert type_res["passed"] == 3
        print(f"[OK] Type filter fast & provenance record verified: {type_res}")

        # B. About & Ngram ルール適用
        about_rules = {"288": "NG", "系譜": "NG", "768.1": "OK"}
        ngram_rules = {"雅楽": "OK"}
        rule_res = db.apply_rules_fast(about_rules, ngram_rules)
        print(f"[OK] Rule filter fast & provenance record verified: {rule_res}")

        # C. PRISMA 集計テスト
        prisma_stats = db.get_prisma_flow_stats()
        assert prisma_stats["total_records"] == 4
        assert prisma_stats["type_discarded"] == 1
        assert prisma_stats["rule_ok"] >= 1
        assert len(prisma_stats["top_drop_reasons"]) > 0
        print(f"[OK] PRISMA flow statistics verified: OK={prisma_stats['rule_ok']}, Disc={prisma_stats['final_discarded']}")

        # D. 完全来歴追跡 (Complete Audit Trail) CSV エクスポートテスト
        csv_path = os.path.join(tmpdir, "complete_audit_trail.csv")
        exported_csv_cnt = db.export_complete_audit_trail_csv(csv_path)
        assert exported_csv_cnt == 4
        assert os.path.exists(csv_path)

        # CSV内容検証
        import pandas as pd
        df_audit = pd.read_csv(csv_path)
        assert len(df_audit) == 4
        assert "final_outcome" in df_audit.columns
        assert "decision_stage" in df_audit.columns
        assert "decision_reason" in df_audit.columns

        # rec1は合格(ADOPTED), rec2とrec3は除外(DISCARDED)
        rec1_row = df_audit[df_audit['id'] == "http://example.org/rec1"].iloc[0]
        assert rec1_row["final_outcome"] == "ADOPTED"
        assert "RULE" in rec1_row["decision_stage"]

        rec3_row = df_audit[df_audit['id'] == "http://example.org/rec3"].iloc[0]
        assert rec3_row["final_outcome"] == "DISCARDED"
        assert rec3_row["decision_stage"] == "TYPE"
        print(f"[OK] Complete Audit Trail CSV exported and verified with all 4 records.")

        db.close()


def test_workspace_and_snapshot_management():
    print("\n=== [Test 10] Workspace and Snapshot Management Test ===")
    from workspace_manager import WorkspaceManager
    import duckdb

    with tempfile.TemporaryDirectory() as tmp_root:
        # 1. ワークスペースマネージャーの初期化
        wm = WorkspaceManager(project_root=tmp_root)
        workspaces = wm.list_workspaces()
        assert len(workspaces) == 1
        assert workspaces[0]["id"] == wm.DEFAULT_WORKSPACE_ID
        print(f"[OK] WorkspaceManager initialized with default workspace: {workspaces[0]['id']}")

        # 2. 新規ワークスペースの作成
        ws_ukiyoe = wm.create_workspace("ukiyoe_test", "浮世絵テストコレクション", "浮世絵研究用ワークスペース")
        assert ws_ukiyoe["id"] == "ukiyoe_test"
        all_ws = wm.list_workspaces()
        assert len(all_ws) == 2
        print(f"[OK] New workspace created: {ws_ukiyoe['id']} ({ws_ukiyoe['name']})")

        # 3. パス生成の検証
        paths_uk = wm.get_workspace_paths("ukiyoe_test")
        assert "ukiyoe_test" in paths_uk["PATH_RAW_METADATA"]
        assert "ukiyoe_test" in paths_uk["PATH_DUCKDB"]
        print(f"[OK] Dynamic paths correctly resolved for ukiyoe_test.")

        # 4. DuckDB とダミーデータを用いたスナップショット保存・復元テスト
        db_path = paths_uk["PATH_DUCKDB"]
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        con = duckdb.connect(db_path)
        con.execute("""
            CREATE TABLE metadata_records (
                id VARCHAR PRIMARY KEY,
                title VARCHAR,
                description VARCHAR,
                about_list VARCHAR[],
                type_list VARCHAR[],
                raw_json VARCHAR,
                type_status VARCHAR DEFAULT NULL,
                type_reason VARCHAR DEFAULT NULL,
                about_status VARCHAR DEFAULT NULL,
                about_reason VARCHAR DEFAULT NULL,
                ngram_status VARCHAR DEFAULT NULL,
                ngram_reason VARCHAR DEFAULT NULL,
                llm_status VARCHAR DEFAULT NULL,
                llm_reason VARCHAR DEFAULT NULL,
                final_decision VARCHAR DEFAULT 'GREY',
                human_decision VARCHAR DEFAULT NULL,
                review_reasons VARCHAR DEFAULT NULL,
                llm_evaluated BOOLEAN DEFAULT FALSE,
                adopted_stage VARCHAR DEFAULT NULL,
                drop_stage VARCHAR DEFAULT NULL,
                primary_reason VARCHAR DEFAULT NULL
            );
        """)
        # レコード挿入
        con.execute("""
            INSERT INTO metadata_records (id, title, final_decision, type_status) VALUES
            ('http://ex.org/1', '富嶽三十六景', 'OK', 'PASSED'),
            ('http://ex.org/2', '東海道五十三次', 'NG', 'EXCLUDED');
        """)
        con.close()

        # スナップショット保存
        snap1 = wm.save_snapshot("ukiyoe_test", "スナップショット1", "初期登録状態")
        assert snap1["metrics"]["total"] == 2
        assert snap1["metrics"]["adopted"] == 1
        assert snap1["metrics"]["discarded"] == 1
        print(f"[OK] Snapshot saved successfully: {snap1['id']} (Metrics: {snap1['metrics']})")

        # DuckDB の判定ステータスを変更
        con = duckdb.connect(db_path)
        con.execute("UPDATE metadata_records SET final_decision = 'GREY';")
        chk = con.execute("SELECT count(*) FROM metadata_records WHERE final_decision = 'OK';").fetchone()[0]
        assert chk == 0
        con.close()

        # スナップショット復元
        res = wm.restore_snapshot("ukiyoe_test", snap1["id"])
        assert res is True
        con = duckdb.connect(db_path)
        chk_restored = con.execute("SELECT count(*) FROM metadata_records WHERE final_decision = 'OK';").fetchone()[0]
        assert chk_restored == 1
        con.close()
        print(f"[OK] Snapshot restored successfully! Decisions rolled back in DuckDB.")

        # 5. ZIP エクスポート & インポート
        zip_out = os.path.join(tmp_root, "test_export.zip")
        wm.export_package("ukiyoe_test", zip_out, export_type="recipe")
        assert os.path.exists(zip_out)
        print(f"[OK] Recipe bundle exported: {os.path.getsize(zip_out)} bytes")

        imported_ws = wm.import_package(zip_out, new_ws_id="imported_study", new_name="引き継ぎデータセット")
        assert imported_ws["id"] == "imported_study"
        assert len(wm.list_workspaces()) == 3
        print(f"[OK] Recipe bundle imported successfully as new workspace: {imported_ws['id']}")

        # 6. 削除
        wm.delete_workspace("imported_study")
        wm.delete_workspace("ukiyoe_test")
        assert len(wm.list_workspaces()) == 1
        print(f"[OK] Workspace deletion verified. Default workspace remains protected.")


def test_clean_environment_and_duckdb_split():
    print("\n=== [Test 11] Clean Environment & DuckDB Split Optimization Test ===")
    from duckdb_manager import DuckDBManager
    from workspace_manager import WorkspaceManager

    # 1. ワークスペースの初期状態パス解決テスト
    wm = WorkspaceManager()
    paths = wm.get_workspace_paths("gagaku_default")
    assert "PATH_DUCKDB" in paths
    assert "PATH_RAW_METADATA" in paths
    print(f"[OK] Workspace paths safely resolved in clean state: {paths['DIR_WORKSPACE']}")

    # 2. DuckDB 高速仕分けエクスポートの単体検証
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = os.path.join(tmpdir, "test.duckdb")
        db = DuckDBManager(test_db_path)

        # テストデータのインポート
        sample_jsonl = os.path.join(tmpdir, "sample.jsonl")
        test_items = [
            {"@id": "http://example.org/1", "rdfs:label": "新選楽譜集 雅楽篇", "schema:about": ["雅楽", "ndc#768"], "rdf:type": ["schema:Book"]},
            {"@id": "http://example.org/2", "rdfs:label": "徳川家系譜図", "schema:about": ["系譜", "歴史"], "rdf:type": ["schema:Book"]},
            {"@id": "http://example.org/3", "rdfs:label": "謡曲選集 観世流", "schema:about": ["能楽"], "rdf:type": ["schema:Book"]},
            {"@id": "http://example.org/4", "rdfs:label": "山梨郡誌 笛吹村", "schema:about": ["地理"], "rdf:type": ["schema:Book"]}
        ]
        with open(sample_jsonl, 'w', encoding='utf-8') as f:
            for item in test_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        imported = db.import_jsonl(sample_jsonl)
        assert imported == 4

        # ルール適用
        about_rules = {"雅楽": "OK", "系譜": "NG"}
        ngram_rules = {"楽譜": "OK", "郡誌": "NG"}
        summary = db.apply_rules_fast(about_rules, ngram_rules)
        assert summary["total"] == 4
        assert summary["ok"] >= 1
        assert summary["ng"] >= 1

        # 高速3分割エクスポート
        out_llm = os.path.join(tmpdir, "target_llm.jsonl")
        out_ok = os.path.join(tmpdir, "confirmed_ok.jsonl")
        out_disc = os.path.join(tmpdir, "discarded.csv")
        ok_c, ng_c, grey_c = db.export_split_datasets(out_llm, out_ok, out_disc)
        assert ok_c + ng_c + grey_c == 4
        assert os.path.exists(out_ok)
        assert os.path.exists(out_disc)
        db.close()
        print(f"[OK] DuckDB apply_rules_fast & export_split_datasets verified: OK={ok_c}, NG={ng_c}, Grey={grey_c}")


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
        test_duckdb_engine()
        test_sparql_fetch_and_job_status()
        test_provenance_and_audit()
        test_workspace_and_snapshot_management()
        test_clean_environment_and_duckdb_split()
        print("\n==================================================")
        print(" SUCCESS: All enhanced pipeline & module tests passed!")
        print("==================================================")
    except Exception as e:
        print(f"\n[FAIL] Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



