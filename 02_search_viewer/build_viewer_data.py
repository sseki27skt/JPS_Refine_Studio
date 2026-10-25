# -*- coding: utf-8 -*-
"""
既存のクレンジングデータから 02_search_viewer/scores_data.json を生成する統合スクリプト
"""

import json
import os
import re

INPUT_JSONL = "data/classical_scores_cleaned.jsonl"
OUTPUT_JSON = "02_search_viewer/scores_data.json"

if not os.path.exists(INPUT_JSONL):
    print(f"入力データ {INPUT_JSONL} が見つかりません。")
    exit(1)

records = []
with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
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
                if any(k in title_desc for k in ["雅楽", "唐楽", "高麗楽", "朗詠", "催馬楽", "笙", "篳篥", "竜笛", "龍笛"]):
                    genre = "雅楽"
                elif any(k in title_desc for k in ["能楽", "謡曲", "謡本", "観世", "宝生", "金剛", "喜多", "狂言"]):
                    genre = "能楽/謡曲"
                elif any(k in title_desc for k in ["三味線", "長唄", "義太夫", "常磐津", "清元", "新内", "地歌", "地唄", "端唄", "俗曲", "小唄"]):
                    genre = "三味線音楽"
                elif any(k in title_desc for k in ["琵琶", "平曲", "平家琵琶", "薩摩琵琶", "筑前琵琶"]):
                    genre = "琵琶楽"
                elif any(k in title_desc for k in ["尺八", "琴古", "都山"]):
                    genre = "尺八楽"
                elif any(k in title_desc for k in ["声明", "伽陀", "法会"]):
                    genre = "声明/仏教音楽"
                else:
                    genre = "古典書籍・一般"

            # 楽器推論
            instruments = data.get("instruments", [])
            if not instruments:
                if any(k in title_desc for k in ["箏", "琴", "十三絃"]): instruments.append("箏/琴")
                if any(k in title_desc for k in ["三味線", "三線"]): instruments.append("三味線")
                if "尺八" in title_desc: instruments.append("尺八")
                if "琵琶" in title_desc: instruments.append("琵琶")
                if "笙" in title_desc: instruments.append("笙")

            # 画像URL
            image = data.get('schema:image', '')
            if isinstance(image, list) and image:
                image = image[0]

            records.append({
                "id": data.get('@id', ''),
                "title": title,
                "description": desc or "詳細記述なし",
                "image": image if isinstance(image, str) else '',
                "url": data.get('@id', ''),
                "provider": provider,
                "genre": genre,
                "instruments": instruments
            })
        except Exception as e:
            continue

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, 'w', encoding='utf-8') as jf:
    json.dump(records, jf, ensure_ascii=False, indent=2)

print(f"[OK] Converted: {len(records)} records exported to {OUTPUT_JSON}.")
