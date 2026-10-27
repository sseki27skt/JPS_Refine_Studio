# -*- coding: utf-8 -*-
"""
既存のクレンジングデータから 02_search_viewer/scores_data.json を生成する統合スクリプト
"""

import json
import os
import re

# Pre-compiled regexes for DuckDB record genre inference
RE_GENRE_DUCKDB_GAGAKU = re.compile(r"雅楽|笙|篳篥|竜笛|龍笛")
RE_GENRE_DUCKDB_NOH = re.compile(r"謡|能|観世|宝生|謡曲|能楽")
RE_GENRE_DUCKDB_SHAMISEN = re.compile(r"三味線|長唄|地歌|地唄|義太夫")
RE_GENRE_DUCKDB_SHAKUHACHI = re.compile(r"尺八|琴古|都山")
RE_GENRE_DUCKDB_BIWA = re.compile(r"琵琶|平曲")
RE_GENRE_DUCKDB_SHOMYO = re.compile(r"声明|伽陀")

# Pre-compiled regexes for JSONL record genre inference
RE_GENRE_JSONL_GAGAKU = re.compile(r"雅楽|唐楽|高麗楽|朗詠|催馬楽|笙|篳篥|竜笛|龍笛")
RE_GENRE_JSONL_NOH = re.compile(r"能楽|謡曲|謡本|観世|宝生|金剛|喜多|狂言")
RE_GENRE_JSONL_SHAMISEN = re.compile(r"三味線|長唄|義太夫|常磐津|清元|新内|地歌|地唄|端唄|俗曲|小唄")
RE_GENRE_JSONL_BIWA = re.compile(r"琵琶|平曲|平家琵琶|薩摩琵琶|筑前琵琶")
RE_GENRE_JSONL_SHAKUHACHI = re.compile(r"尺八|琴古|都山")
RE_GENRE_JSONL_SHOMYO = re.compile(r"声明|伽陀|法会")

# Pre-compiled regexes for instrument inference
RE_INST_KOTO = re.compile(r"箏|琴|十三絃")
RE_INST_SHAMISEN = re.compile(r"三味線|三線")

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "01_cleansing_studio")))
from modules.duckdb_manager import DuckDBManager
from modules.sparql_collector import get_acquisition_manifest

DUCKDB_PATH = "data/metadata_store.duckdb"
POSSIBLE_JSONLS = [
    "data/classical_scores_cleaned.jsonl",
    "data/verified_records.jsonl",
    "data/ngram_filtered.jsonl",
    "data/about_filtered.jsonl",
    "data/benchmark_sample_10k.jsonl",
    "data/raw_metadata.jsonl"
]
OUTPUT_JSON = "02_search_viewer/scores_data.json"
MANIFEST_PATH = "data/acquisition_manifest.json"
PRISMA_JSON_PATH = "data/prisma_flow_summary.json"

records = []

# 1. Try extracting from DuckDB
if os.path.exists(DUCKDB_PATH):
    try:
        db = DuckDBManager(DUCKDB_PATH)
        cnt = db.get_record_count()
        if cnt > 0:
            print(f"[Info] DuckDB ({DUCKDB_PATH}) から採択レコードを抽出します (総レコード: {cnt:,} 件)...")
            query = """
                SELECT 
                    id, 
                    title, 
                    description, 
                    coalesce(review_reasons, primary_reason, matched_reason, 'ルール合致') AS p_reason,
                    coalesce(adopted_stage, 'RULE') AS p_stage,
                    raw_json
                FROM metadata_records
                WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格'
                LIMIT 500;
            """
            rows = db.conn.execute(query).fetchall()
            for r in rows:
                item_id, title, desc, p_reason, p_stage, raw_j = r
                raw_data = json.loads(raw_j) if raw_j else {}

                provider = "Japan Search"
                source = raw_data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                if isinstance(source, dict):
                    prov_val = source.get('schema:provider', '')
                    if prov_val:
                        provider = str(prov_val).split('/')[-1]

                genre = "古典資料/その他"
                t_desc = (str(title) + " " + str(desc)).lower()
                if RE_GENRE_DUCKDB_GAGAKU.search(t_desc): genre = "雅楽"
                elif RE_GENRE_DUCKDB_NOH.search(t_desc): genre = "能楽/謡曲"
                elif RE_GENRE_DUCKDB_SHAMISEN.search(t_desc): genre = "三味線音楽"
                elif RE_GENRE_DUCKDB_SHAKUHACHI.search(t_desc): genre = "尺八楽"
                elif RE_GENRE_DUCKDB_BIWA.search(t_desc): genre = "琵琶楽"
                elif RE_GENRE_DUCKDB_SHOMYO.search(t_desc): genre = "声明/仏教音楽"

                instruments = []
                if RE_INST_KOTO.search(t_desc): instruments.append("箏/琴")
                if RE_INST_SHAMISEN.search(t_desc): instruments.append("三味線")
                if "尺八" in t_desc: instruments.append("尺八")
                if "琵琶" in t_desc: instruments.append("琵琶")
                if "笙" in t_desc: instruments.append("笙")

                image = raw_data.get('schema:image', '')
                if isinstance(image, list) and image:
                    image = image[0]

                records.append({
                    "id": item_id,
                    "title": title or "無題資料",
                    "description": str(desc)[:250] if desc else "詳細記述なし",
                    "provider": provider,
                    "genre": genre,
                    "instruments": instruments,
                    "url": item_id,
                    "image": image if isinstance(image, str) else '',
                    "provenance": {
                        "stage": p_stage,
                        "reason": p_reason,
                        "confidence": "HIGH" if p_stage in ["RULE", "HUMAN"] else "MEDIUM"
                    }
                })

            # Also export PRISMA flow and complete audit trail if needed
            prisma_stats = db.get_prisma_flow_stats()
            with open(PRISMA_JSON_PATH, 'w', encoding='utf-8') as pf:
                json.dump(prisma_stats, pf, ensure_ascii=False, indent=2)
            db.export_complete_audit_trail_csv("data/complete_audit_trail.csv")
            print(f"[OK] PRISMA flow summary & Audit Trail exported.")

            # Create acquisition_manifest.json if missing
            if not os.path.exists(MANIFEST_PATH) and os.path.exists("data/current_fetch_params.json"):
                with open("data/current_fetch_params.json", 'r', encoding='utf-8') as cf:
                    c_params = json.load(cf)
                manifest_obj = {
                    "dataset_name": "Japan Search Cleansed Collection (古典楽譜資料)",
                    "created_at": "2026-10-26 10:00:00",
                    "endpoint": "https://jpsearch.go.jp/rdf/sparql/",
                    "initial_condition": {
                        "keywords": c_params.get("keywords", [])[:10],
                        "target_ndc": c_params.get("target_ndc", ["768", "766", "763"]),
                        "exclude_ndc": c_params.get("exclude_ndc", ["288", "720", "400"]),
                        "regex_patterns": [".*(譜|楽|本).*"]
                    },
                    "metrics": {
                        "total_target_uris": cnt,
                        "success_count": cnt
                    }
                }
                with open(MANIFEST_PATH, 'w', encoding='utf-8') as mf:
                    json.dump(manifest_obj, mf, ensure_ascii=False, indent=2)
                print(f"[OK] Acquisition manifest generated: {MANIFEST_PATH}")

            db.close()
    except Exception as e:
        print(f"[Warn] DuckDB reading failed: {e}")

# 2. If no records from DuckDB, fallback to JSONL files
if not records:
    target_jsonl = None
    for p in POSSIBLE_JSONLS:
        if os.path.exists(p):
            target_jsonl = p
            break

    if not target_jsonl:
        print(f"[Error] 入力データ（DuckDB または JSONL）が見つかりません。")
        exit(1)

    print(f"[Info] JSONL ({target_jsonl}) からレコードを生成します...")
    with open(target_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                
                # タイトルの取得
                label = data.get('rdfs:label')
                name = data.get('schema:name')
                title = str(label) if label else (str(name) if name else "無題資料")
                if isinstance(name, list) and name:
                    title = str(name[0])
                elif isinstance(label, list) and label:
                    title = str(label[0])

                # 説明文の取得
                desc_val = data.get('schema:description', '') or data.get('description', '')
                if isinstance(desc_val, list):
                    desc = " ".join([str(x) for x in desc_val])
                else:
                    desc = str(desc_val)
                
                desc = re.sub(r'<[^>]*>', '', desc)
                if len(desc) > 250:
                    desc = desc[:250] + "..."

                # 提供元の取得
                provider = "Japan Search"
                source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                if isinstance(source, dict):
                    prov_val = source.get('schema:provider', '')
                    if prov_val:
                        provider = str(prov_val).split('/')[-1]

                # ジャンル推論
                genre = data.get("genre", "その他/不明")
                title_desc = (title + " " + desc).lower()
                
                if genre == "その他/不明" or not genre:
                    if RE_GENRE_JSONL_GAGAKU.search(title_desc):
                        genre = "雅楽"
                    elif RE_GENRE_JSONL_NOH.search(title_desc):
                        genre = "能楽/謡曲"
                    elif RE_GENRE_JSONL_SHAMISEN.search(title_desc):
                        genre = "三味線音楽"
                    elif RE_GENRE_JSONL_BIWA.search(title_desc):
                        genre = "琵琶楽"
                    elif RE_GENRE_JSONL_SHAKUHACHI.search(title_desc):
                        genre = "尺八楽"
                    elif RE_GENRE_JSONL_SHOMYO.search(title_desc):
                        genre = "声明/仏教音楽"
                    else:
                        genre = "古典書籍・一般"

                # 楽器推論
                instruments = data.get("instruments", [])
                if not instruments:
                    if RE_INST_KOTO.search(title_desc): instruments.append("箏/琴")
                    if RE_INST_SHAMISEN.search(title_desc): instruments.append("三味線")
                    if "尺八" in title_desc: instruments.append("尺八")
                    if "琵琶" in title_desc: instruments.append("琵琶")
                    if "笙" in title_desc: instruments.append("笙")

                # 画像URL
                image = data.get('schema:image', '')
                if isinstance(image, list) and image:
                    image = image[0]

                # 来歴情報の取得
                prov = data.get('provenance')
                if not prov:
                    r_reason = data.get('review_reasons', data.get('reason', 'ルール合致'))
                    prov = {
                        "stage": "RULE",
                        "reason": r_reason,
                        "confidence": "HIGH"
                    }

                records.append({
                    "id": data.get('@id', ''),
                    "title": title,
                    "description": desc or "詳細記述なし",
                    "image": image if isinstance(image, str) else '',
                    "url": data.get('@id', ''),
                    "provider": provider,
                    "genre": genre,
                    "instruments": instruments,
                    "provenance": prov
                })
            except Exception as e:
                continue

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, 'w', encoding='utf-8') as jf:
    json.dump(records, jf, ensure_ascii=False, indent=2)

print(f"[OK] Converted: {len(records)} records exported to {OUTPUT_JSON}.")
