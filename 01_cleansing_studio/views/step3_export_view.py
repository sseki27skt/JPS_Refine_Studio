# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 3: データエクスポートビュー
"""
import json
import os
import pandas as pd
import streamlit as st

from components.file_utils import count_lines, safe_save_json

def render_step3_view(paths: dict):
    """Step 5 画面の描画"""
    st.title("Step 5: 統合検索用データエクスポート")
    st.markdown("精緻化された確定メタデータを検索ポータル（`02_search_viewer`）用JSON形式へ構造化出力し、一括利用可能な形式へ変換します。")

    verified_jsonl_path = paths['PATH_VERIFIED_JSONL']
    llm_judgments_path = paths['PATH_LLM_JUDGMENTS']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    raw_metadata_path = paths['PATH_RAW_METADATA']
    export_json_path = paths['PATH_EXPORT_JSON']
    data_dir = os.path.dirname(verified_jsonl_path)

    source_path = verified_jsonl_path if os.path.exists(verified_jsonl_path) else (
        ngram_filtered_path if os.path.exists(ngram_filtered_path) else (
            about_filtered_path if os.path.exists(about_filtered_path) else (
                type_filtered_path if os.path.exists(type_filtered_path) else raw_metadata_path
            )
        )
    )
    if not os.path.exists(source_path):
        st.warning("エクスポート対象データが存在しません。Step 1 でメタデータを取得してください。")
        st.stop()

    source_line_count = count_lines(source_path)
    st.info(f"検出されたデータソース: `{source_path}` (全 {source_line_count:,} 件)")

    if st.button("統合検索用 scores_data.json の生成・エクスポート実行", type="primary", use_container_width=True):
        records = []
        with open(source_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    
                    label = data.get('rdfs:label', data.get('schema:name', 'No Title'))
                    title = label[0] if isinstance(label, list) and label else str(label)
                    
                    desc_val = data.get('schema:description', '')
                    desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)
                    
                    provider = ''
                    source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                    if isinstance(source, dict):
                        provider = str(source.get('schema:provider', '')).split('/')[-1]

                    genre = "古典資料/その他"
                    if any(k in title for k in ["雅楽", "笙", "篳篥"]): genre = "雅楽"
                    elif any(k in title for k in ["謡", "能", "観世"]): genre = "能楽/謡曲"
                    elif any(k in title for k in ["三味線", "長唄", "地歌"]): genre = "三味線音楽"

                    item_id = data.get('@id', data.get('id', ''))
                    records.append({
                        "id": item_id,
                        "title": title,
                        "description": desc[:300] if desc else "詳細記述なし",
                        "provider": provider or "Japan Search",
                        "genre": genre,
                        "url": item_id
                    })
                except Exception:
                    continue

        safe_save_json(records, export_json_path)

        path_export_csv = f"{data_dir}/cleaned_metadata.csv"
        df_export = pd.DataFrame(records)
        df_export.to_csv(path_export_csv, index=False, encoding='utf-8-sig')

        st.success(f"データエクスポート完了: 全 {len(records):,} 件のデータを `{export_json_path}` および `{path_export_csv}` に出力しました。")

    st.write("---")
    st.subheader("成果物データの直接ダウンロード")
    st.markdown("生成された精緻化結果ファイルをローカル環境へ直接ダウンロードできます。")

    c_dl1, c_dl2, c_dl3 = st.columns(3)
    path_export_csv = f"{data_dir}/cleaned_metadata.csv"

    with c_dl1:
        if os.path.exists(export_json_path):
            with open(export_json_path, 'rb') as f:
                st.download_button(
                    label="scores_data.json のダウンロード",
                    data=f,
                    file_name="scores_data.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.button("scores_data.json (未出力)", disabled=True, use_container_width=True)

    with c_dl2:
        if os.path.exists(path_export_csv):
            with open(path_export_csv, 'rb') as f:
                st.download_button(
                    label="cleaned_metadata.csv のダウンロード",
                    data=f,
                    file_name="cleaned_metadata.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.button("cleaned_metadata.csv (未出力)", disabled=True, use_container_width=True)

    with c_dl3:
        if os.path.exists(verified_jsonl_path):
            with open(verified_jsonl_path, 'rb') as f:
                st.download_button(
                    label="human_verified_cleaned.jsonl のダウンロード",
                    data=f,
                    file_name="human_verified_cleaned.jsonl",
                    mime="application/jsonlines",
                    use_container_width=True
                )
        else:
            st.button("human_verified_cleaned.jsonl (未確定)", disabled=True, use_container_width=True)
