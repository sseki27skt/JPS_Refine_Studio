# -*- coding: utf-8 -*-
"""
ベンチマークスクリプト: フィルタリング処理の速度・メモリ測定
(旧方式: JSONL逐次処理 vs 新方式: DuckDB高速エンジン)
"""

import os
import sys
import time
import json
import random
import tracemalloc

# パス追加
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(CURRENT_DIR, "modules")
sys.path.insert(0, MODULES_DIR)

from rule_filter import extract_about_keywords_from_jsonl, split_dataset_by_rules
from ngram_filter import extract_ngrams_from_jsonl


def generate_benchmark_dataset(output_path: str, count: int = 10000):
    """
    実データの傾向を模したベンチマーク用メタデータセット (10,000件) を生成
    """
    if os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
        print(f"[Dataset] Existing benchmark dataset found: {output_path}")
        return

    print(f"[Dataset] Generating {count:,} benchmark records to {output_path}...")
    sample_titles = [
        "新選楽譜集 第{i}巻 雅楽篇",
        "徳川家系譜図 巻之{i}",
        "謡曲集 {i} 観世流能楽譜",
        "甲斐国山梨郡誌 笛吹村沿革 第{i}編",
        "三味線名曲選 地歌手附 {i}",
        "明治美術画譜 第{i}集",
        "琴古流尺八譜 秘曲集 {i}",
        "明治物価年譜 経済統計資料 第{i}巻",
        "東大寺声明伽陀 声明譜 第{i}本",
        "小野家過去帳 系譜考 {i}"
    ]

    sample_abouts = [
        ["雅楽", "ndc#768.1", "http://jla.or.jp/data/ndc#760"],
        ["系譜", "歴史--日本--江戸時代", "徳川家"],
        ["能楽", "謡曲", "観世流", "766.1"],
        ["地理--山梨県", "笛吹市", "地方史"],
        ["三味線音楽", "地歌", "端唄", "768.2"],
        ["美術--絵画--画譜", "浮世絵", "720"],
        ["尺八楽", "琴古流", "768.3"],
        ["年譜", "経済--日本", "物価"],
        ["仏教音楽", "声明", "法会"],
        ["家譜", "系図", "歴史"]
    ]

    sample_types = [
        ["schema:Book", "jps:ClassicalWork"],
        ["schema:Book", "jps:HistoricalRecord"],
        ["schema:Book", "jps:MusicalScore"],
        ["schema:Map", "jps:Document"],
        ["schema:Book", "jps:Manuscript"]
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for i in range(1, count + 1):
            pattern_idx = i % len(sample_titles)
            title = sample_titles[pattern_idx].format(i=i)
            abouts = sample_abouts[pattern_idx]
            types = sample_types[i % len(sample_types)]
            
            # ランダムにキーワードを追加して多様性を持たせる
            extra_about = [f"分野_{random.randint(1, 20)}", f"地域_{random.randint(1, 10)}"]
            
            record = {
                "@id": f"http://example.org/item/{i:06d}",
                "rdfs:label": title,
                "schema:name": title,
                "schema:description": f"これは第{i}号資料の書誌説明文です。詳細なメタデータと解説が含まれます。",
                "schema:about": abouts + extra_about,
                "rdf:type": types,
                "status": "success"
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[Dataset] Generated {count:,} records successfully.")


def run_legacy_benchmark(dataset_path: str, about_rules_path: str, ngram_rules_path: str):
    """現行方式 (JSONL逐次処理) のベンチマーク計測"""
    print("\n" + "=" * 60)
    print(" [1] 現行方式 (JSONL逐次読み込み ＆ Pythonループ) ベンチマーク開始")
    print("=" * 60)

    results = {}

    # 1. Aboutキーワード抽出 ＆ 集計
    tracemalloc.start()
    t0 = time.time()
    kw_counts = extract_about_keywords_from_jsonl(dataset_path)
    t_about = time.time() - t0
    _, peak_mem_about = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["about_extract"] = {
        "time_sec": t_about,
        "mem_mb": peak_mem_about / (1024 * 1024),
        "unique_keywords": len(kw_counts),
        "top5": kw_counts[:5]
    }
    print(f" (1) Aboutキーワード集計: {t_about:.3f} 秒 (ピークメモリ: {results['about_extract']['mem_mb']:.2f} MB, {len(kw_counts)} 種類)")

    # 2. N-gram抽出 ＆ 集計
    tracemalloc.start()
    t0 = time.time()
    ngrams = extract_ngrams_from_jsonl(dataset_path, min_n=2, max_n=3)
    t_ngram = time.time() - t0
    _, peak_mem_ngram = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    bigram_cnt = len(ngrams.get(2, []))
    trigram_cnt = len(ngrams.get(3, []))
    results["ngram_extract"] = {
        "time_sec": t_ngram,
        "mem_mb": peak_mem_ngram / (1024 * 1024),
        "bigram_types": bigram_cnt,
        "trigram_types": trigram_cnt
    }
    print(f" (2) N-gram抽出・集計: {t_ngram:.3f} 秒 (ピークメモリ: {results['ngram_extract']['mem_mb']:.2f} MB)")

    # 3. ルール適用（データ3分割: OK / NG / Grey）
    bench_dir = os.path.join(CURRENT_DIR, "..", "data", "benchmark_tmp")
    os.makedirs(bench_dir, exist_ok=True)
    tmp_target_llm = os.path.join(bench_dir, "bench_target_llm.jsonl")
    tmp_confirmed_ok = os.path.join(bench_dir, "bench_confirmed_ok.jsonl")
    tmp_discarded_csv = os.path.join(bench_dir, "bench_discarded.csv")

    tracemalloc.start()
    t0 = time.time()
    ok_cnt, ng_cnt, grey_cnt = split_dataset_by_rules(
        input_jsonl_path=dataset_path,
        about_rules_path=about_rules_path,
        ngram_rules_path=ngram_rules_path,
        output_target_for_llm_jsonl=tmp_target_llm,
        output_confirmed_ok_jsonl=tmp_confirmed_ok,
        output_discarded_csv=tmp_discarded_csv
    )
    t_split = time.time() - t0
    _, peak_mem_split = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["split_rules"] = {
        "time_sec": t_split,
        "mem_mb": peak_mem_split / (1024 * 1024),
        "ok": ok_cnt,
        "ng": ng_cnt,
        "grey": grey_cnt
    }
    print(f" (3) ルール適用・3分割: {t_split:.3f} 秒 (ピークメモリ: {results['split_rules']['mem_mb']:.2f} MB, OK={ok_cnt}, NG={ng_cnt}, Grey={grey_cnt})")

    # 4. 査読ポータル (Step 4: 10,000件のロード ＆ 1ページ20件表示・検索)
    from review_portal import load_merged_review_data
    tracemalloc.start()
    t0 = time.time()
    legacy_records = load_merged_review_data(dataset_path)
    # 検索・ページングシミュレーション (タイトル検索 '第' + 20件)
    filtered = [r for r in legacy_records if "第" in r["title"] and r["status"] == "合格"]
    page_1 = filtered[:20]
    t_review = time.time() - t0
    _, peak_mem_review = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["review_portal"] = {
        "time_sec": t_review,
        "mem_mb": peak_mem_review / (1024 * 1024),
        "total_records": len(legacy_records),
        "filtered_count": len(filtered)
    }
    print(f" (4) 査読ポータル (全件ロード ＆ 検索ページング): {t_review:.3f} 秒 (ピークメモリ: {results['review_portal']['mem_mb']:.2f} MB)")

    # クリーンアップ
    for p in [tmp_target_llm, tmp_confirmed_ok, tmp_discarded_csv]:
        if os.path.exists(p):
            os.remove(p)

    return results


def run_duckdb_benchmark(dataset_path: str, about_rules_path: str, ngram_rules_path: str):
    """新方式 (DuckDBエンジン) のベンチマーク計測"""
    from duckdb_manager import DuckDBManager

    print("\n" + "=" * 60)
    print(" [2] 新方式 (DuckDB 高速エンジン) ベンチマーク開始")
    print("=" * 60)

    results = {}

    # ルールロード
    with open(about_rules_path, 'r', encoding='utf-8') as f:
        about_rules = json.load(f)
    with open(ngram_rules_path, 'r', encoding='utf-8') as f:
        ngram_rules = json.load(f)

    # 0. DuckDB初期化 ＆ インポート
    db = DuckDBManager(":memory:")

    tracemalloc.start()
    t0 = time.time()
    imported = db.import_jsonl(dataset_path)
    t_import = time.time() - t0
    _, peak_mem_import = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["import"] = {
        "time_sec": t_import,
        "mem_mb": peak_mem_import / (1024 * 1024),
        "count": imported
    }
    print(f" (0) DuckDB バルクインポート: {t_import:.3f} 秒 (ピークメモリ: {results['import']['mem_mb']:.2f} MB, {imported:,} 件)")

    # 1. Aboutキーワード抽出 ＆ 集計
    tracemalloc.start()
    t0 = time.time()
    kw_counts = db.get_about_keyword_counts()
    t_about = time.time() - t0
    _, peak_mem_about = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["about_extract"] = {
        "time_sec": t_about,
        "mem_mb": peak_mem_about / (1024 * 1024),
        "unique_keywords": len(kw_counts),
        "top5": kw_counts[:5]
    }
    print(f" (1) Aboutキーワード集計 (SQL): {t_about:.3f} 秒 (ピークメモリ: {results['about_extract']['mem_mb']:.2f} MB, {len(kw_counts)} 種類)")

    # 2. N-gram抽出 ＆ 集計
    tracemalloc.start()
    t0 = time.time()
    ngrams = db.extract_ngrams(min_n=2, max_n=3)
    t_ngram = time.time() - t0
    _, peak_mem_ngram = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    bigram_cnt = len(ngrams.get(2, []))
    trigram_cnt = len(ngrams.get(3, []))
    results["ngram_extract"] = {
        "time_sec": t_ngram,
        "mem_mb": peak_mem_ngram / (1024 * 1024),
        "bigram_types": bigram_cnt,
        "trigram_types": trigram_cnt
    }
    print(f" (2) N-gram抽出・集計: {t_ngram:.3f} 秒 (ピークメモリ: {results['ngram_extract']['mem_mb']:.2f} MB)")

    # 3. ルール適用（データ3分割: OK / NG / Grey）
    bench_dir = os.path.join(CURRENT_DIR, "..", "data", "benchmark_tmp")
    os.makedirs(bench_dir, exist_ok=True)
    tmp_target_llm = os.path.join(bench_dir, "bench_duckdb_target_llm.jsonl")
    tmp_confirmed_ok = os.path.join(bench_dir, "bench_duckdb_confirmed_ok.jsonl")
    tmp_discarded_csv = os.path.join(bench_dir, "bench_duckdb_discarded.csv")

    tracemalloc.start()
    t0 = time.time()
    split_summary = db.apply_rules_fast(about_rules, ngram_rules)
    db.export_split_datasets(tmp_target_llm, tmp_confirmed_ok, tmp_discarded_csv)
    t_split = time.time() - t0
    _, peak_mem_split = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["split_rules"] = {
        "time_sec": t_split,
        "mem_mb": peak_mem_split / (1024 * 1024),
        "ok": split_summary["ok"],
        "ng": split_summary["ng"],
        "grey": split_summary["grey"]
    }
    print(f" (3) ルール適用・3分割 (DuckDB+高速正規表現): {t_split:.3f} 秒 (ピークメモリ: {results['split_rules']['mem_mb']:.2f} MB, OK={split_summary['ok']}, NG={split_summary['ng']}, Grey={split_summary['grey']})")

    # 4. 査読ポータル (Step 4: 10,000件のメトリクス集計 ＆ 1ページ20件サーバーサイド検索)
    tracemalloc.start()
    t0 = time.time()
    metrics = db.get_review_metrics()
    total_q, page_recs = db.query_review_records(
        filter_type="現在『合格』のデータのみ",
        search_query="第",
        page=1,
        page_size=20
    )
    t_review = time.time() - t0
    _, peak_mem_review = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["review_portal"] = {
        "time_sec": t_review,
        "mem_mb": peak_mem_review / (1024 * 1024),
        "total_records": metrics["total"],
        "filtered_count": total_q
    }
    print(f" (4) 査読ポータル (SQLメトリクス ＆ サーバーサイド検索): {t_review:.3f} 秒 (ピークメモリ: {results['review_portal']['mem_mb']:.2f} MB)")

    # クリーンアップ
    for p in [tmp_target_llm, tmp_confirmed_ok, tmp_discarded_csv]:
        if os.path.exists(p):
            os.remove(p)

    db.close()
    return results


def print_comparison(legacy: dict, duckdb_res: dict):
    """比較レポートのコンソール出力"""
    print("\n" + "=" * 75)
    print(" 🚀 ベンチマーク比較レポート (10,000件のメタデータ処理)")
    print("=" * 75)
    print(f"{'処理項目':<22} | {'旧方式 (JSONL)':<15} | {'新方式 (DuckDB)':<15} | {'改善率 / 高速化':<15}")
    print("-" * 75)

    # About集計
    t_leg_abt = legacy["about_extract"]["time_sec"]
    t_duc_abt = duckdb_res["about_extract"]["time_sec"]
    speedup_abt = t_leg_abt / t_duc_abt if t_duc_abt > 0 else float('inf')
    print(f"{'Aboutキーワード集計':<20} | {t_leg_abt:>10.3f} 秒    | {t_duc_abt:>10.3f} 秒    | {speedup_abt:>6.1f}x 高速化 ⚡")

    # N-gram集計
    t_leg_ng = legacy["ngram_extract"]["time_sec"]
    t_duc_ng = duckdb_res["ngram_extract"]["time_sec"]
    speedup_ng = t_leg_ng / t_duc_ng if t_duc_ng > 0 else float('inf')
    print(f"{'N-gram抽出・集計':<22} | {t_leg_ng:>10.3f} 秒    | {t_duc_ng:>10.3f} 秒    | {speedup_ng:>6.1f}x 高速化 ⚡")

    # ルール適用
    t_leg_sp = legacy["split_rules"]["time_sec"]
    t_duc_sp = duckdb_res["split_rules"]["time_sec"]
    speedup_sp = t_leg_sp / t_duc_sp if t_duc_sp > 0 else float('inf')
    print(f"{'ルール適用・3分割':<21} | {t_leg_sp:>10.3f} 秒    | {t_duc_sp:>10.3f} 秒    | {speedup_sp:>6.1f}x 高速化 (🔥)")

    # 査読ポータル (Step 4)
    if "review_portal" in legacy and "review_portal" in duckdb_res:
        t_leg_rev = legacy["review_portal"]["time_sec"]
        t_duc_rev = duckdb_res["review_portal"]["time_sec"]
        speedup_rev = t_leg_rev / t_duc_rev if t_duc_rev > 0 else float('inf')
        print(f"{'Step 4 査読表示・検索':<20} | {t_leg_rev:>10.3f} 秒    | {t_duc_rev:>10.3f} 秒    | {speedup_rev:>6.1f}x 高速化 (🔥)")

    # 合計処理時間
    total_leg = t_leg_abt + t_leg_ng + t_leg_sp
    total_duc = duckdb_res["import"]["time_sec"] + t_duc_abt + t_duc_ng + t_duc_sp
    total_speedup = total_leg / total_duc if total_duc > 0 else float('inf')
    print("-" * 75)
    print(f"{'全工程合計 (インポート込)':<18} | {total_leg:>10.3f} 秒    | {total_duc:>10.3f} 秒    | {total_speedup:>6.1f}x 高速化")
    print("=" * 75)

    # 判定結果の一致検証
    print("\n【判定結果の整合性チェック】")
    ok_match = (legacy["split_rules"]["ok"] == duckdb_res["split_rules"]["ok"])
    ng_match = (legacy["split_rules"]["ng"] == duckdb_res["split_rules"]["ng"])
    grey_match = (legacy["split_rules"]["grey"] == duckdb_res["split_rules"]["grey"])
    print(f"- OK 判定数:  旧 {legacy['split_rules']['ok']} 件 vs 新 {duckdb_res['split_rules']['ok']} 件 -> {'✅ 完全一致' if ok_match else '❌ 不一致'}")
    print(f"- NG 判定数:  旧 {legacy['split_rules']['ng']} 件 vs 新 {duckdb_res['split_rules']['ng']} 件 -> {'✅ 完全一致' if ng_match else '❌ 不一致'}")
    print(f"- Grey 判定数: 旧 {legacy['split_rules']['grey']} 件 vs 新 {duckdb_res['split_rules']['grey']} 件 -> {'✅ 完全一致' if grey_match else '❌ 不一致'}")


if __name__ == "__main__":
    DATASET_PATH = os.path.join(CURRENT_DIR, "..", "data", "benchmark_sample_10k.jsonl")
    ABOUT_RULES = os.path.join(CURRENT_DIR, "rules", "about_rules.json")
    NGRAM_RULES = os.path.join(CURRENT_DIR, "rules", "ngram_rules.json")

    # 1. ベンチマークデータの生成 (10,000件)
    generate_benchmark_dataset(DATASET_PATH, count=10000)

    # 2. 既存のLegacy結果があればロード、なければ実行
    legacy_json = os.path.join(CURRENT_DIR, "..", "docs", "filter_process_optimization", "legacy_benchmark.json")
    if os.path.exists(legacy_json):
        with open(legacy_json, 'r', encoding='utf-8') as f:
            legacy_res = json.load(f)
        print("\n[OK] Loaded existing legacy benchmark results.")
    else:
        legacy_res = run_legacy_benchmark(DATASET_PATH, ABOUT_RULES, NGRAM_RULES)
        with open(legacy_json, 'w', encoding='utf-8') as f:
            json.dump(legacy_res, f, ensure_ascii=False, indent=2)

    # 3. DuckDB方式の測定
    duckdb_res = run_duckdb_benchmark(DATASET_PATH, ABOUT_RULES, NGRAM_RULES)
    duckdb_json = os.path.join(CURRENT_DIR, "..", "docs", "filter_process_optimization", "duckdb_benchmark.json")
    with open(duckdb_json, 'w', encoding='utf-8') as f:
        json.dump(duckdb_res, f, ensure_ascii=False, indent=2)

    # 4. 比較レポートの表示
    print_comparison(legacy_res, duckdb_res)
