# -*- coding: utf-8 -*-
"""
JS-Refine Studio - Step 5: 統合検索用データ ＆ 再現性・監査パッケージエクスポートビュー
"""
import json
import os
import pandas as pd
import streamlit as st

from components.file_utils import count_lines, safe_save_json
from modules.duckdb_manager import DuckDBManager
from modules.sparql_collector import get_acquisition_manifest, DEFAULT_MANIFEST_FILE


def generate_prisma_markdown_report(stats: dict, manifest: dict = None) -> str:
    total = stats.get("total_records", 0)
    type_disc = stats.get("type_discarded", 0)
    type_pass = stats.get("type_passed", 0)
    rule_ok = stats.get("rule_ok", 0)
    rule_ng = stats.get("rule_ng", 0)
    rule_grey = stats.get("rule_grey", 0)
    llm_total = stats.get("llm_evaluated_total", 0)
    llm_pass = stats.get("llm_passed", 0)
    llm_disc = stats.get("llm_discarded", 0)
    human_ov = stats.get("human_override_count", 0)
    final_ad = stats.get("final_adopted", 0)
    final_disc = stats.get("final_discarded", 0)
    top_reasons = stats.get("top_drop_reasons", [])

    created_at = manifest.get("created_at", "不明") if manifest else "不明"
    endpoint = manifest.get("endpoint", "https://jpsearch.go.jp/rdf/sparql/") if manifest else "https://jpsearch.go.jp/rdf/sparql/"

    md = f"""# メタデータ精緻化・絞り込みプロセス PRISMAフローレポート

## 1. 概要 (Overview)
- **データセット名**: Japan Search Cleansed Collection
- **データ取得日時**: {created_at}
- **SPARQLエンドポイント**: `{endpoint}`
- **初期同定件数 (Identification)**: {total:,} 件
- **最終採択件数 (Included)**: {final_ad:,} 件 (採択率: {final_ad/max(1, total):.1%})
- **総除外件数 (Excluded)**: {final_disc:,} 件 (除外率: {final_disc/max(1, total):.1%})

---

## 2. 系統的絞り込みフロー (PRISMA 2020 Flow Diagram)

```mermaid
flowchart TD
    A["【初期同定】<br>Japan Search SPARQL取得<br>(N = {total:,})"] --> B["【Stage 1: データ種別除外】<br>非該当 rdf:type の除外<br>(除外: {type_disc:,} 件)"]
    B --> C["【Stage 1 通過母集団】<br>(N = {type_pass:,})"]
    C --> D["【Stage 2: ルールベース判定】<br>About (NDC/NDLNA) ＆ タイトル語彙<br>(合致合格: {rule_ok:,} 件 / 除外: {rule_ng:,} 件)"]
    D --> E["【Stage 3: LLM推論】<br>判定保留 (GREY) 群のセマンティック分類<br>(投入: {llm_total:,} 件 ➔ 合格: {llm_pass:,} 件 / 除外: {llm_disc:,} 件)"]
    D -. 合格バイパス .-> F["【Stage 4: 専門家査読】<br>人手確認・手動オーバーライド<br>(修正: {human_ov:,} 件)"]
    E --> F
    F --> G["【最終採択データセット】<br>真正楽譜資料メタデータ<br>(N = {final_ad:,} 件)"]
```

---

## 3. 段階別集計テーブル (Stage-by-Stage Attrition Table)

| 段階 (Stage) | 投入件数 | 通過・採択件数 | 除外件数 | 主な基準・理由 |
| :--- | :---: | :---: | :---: | :--- |
| **初期同定 (SPARQL)** | - | **{total:,}** | 0 | SPARQL検索語・包含/除外NDC |
| **Stage 1: データ種別 (Type)** | {total:,} | **{type_pass:,}** | {type_disc:,} | 記事・公演・絵画・絵葉書等の種別除外 |
| **Stage 2: ルール判定 (About/Ngram)** | {type_pass:,} | **{rule_ok:,}** (OK) | {rule_ng:,} | NDC分類(家譜・画譜等)、タイトル接尾辞 |
| **Stage 3: LLM推論 (Grey)** | {llm_total:,} | **{llm_pass:,}** | {llm_disc:,} | セマンティック推論・解題記述判定 |
| **Stage 4: 専門家査読** | - | **{final_ad:,}** | - | 手動修正 ({human_ov:,} 件修正) |

---

## 4. 主な除外理由ランキング (Top Exclusion Reasons)

"""
    for idx, (r, c) in enumerate(top_reasons, 1):
        md += f"{idx}. **{r}**: {c:,} 件 ({c/max(1, final_disc):.1%})\n"

    return md


def render_step3_view(paths: dict):
    """Step 5 画面の描画"""
    st.title("Step 5: データエクスポート ＆ 再現性・監査パッケージ生成")
    st.markdown("精緻化された確定メタデータを検索ポータル（`02_search_viewer`）用JSON形式へ構造化出力するとともに、**論文・成果公開用の完全追跡データ（Audit Trail CSV）およびPRISMAフローレポート**を一括生成します。")

    verified_jsonl_path = paths['PATH_VERIFIED_JSONL']
    llm_judgments_path = paths['PATH_LLM_JUDGMENTS']
    ngram_filtered_path = paths['PATH_NGRAM_FILTERED']
    about_filtered_path = paths['PATH_ABOUT_FILTERED']
    type_filtered_path = paths.get('PATH_TYPE_FILTERED', 'data/type_filtered.jsonl')
    raw_metadata_path = paths['PATH_RAW_METADATA']
    export_json_path = paths['PATH_EXPORT_JSON']
    duckdb_path = paths.get('PATH_DUCKDB', os.path.join(os.path.dirname(raw_metadata_path), "metadata_store.duckdb"))
    manifest_path = paths.get('PATH_ACQUISITION_MANIFEST', os.path.join(os.path.dirname(raw_metadata_path), "acquisition_manifest.json"))
    data_dir = os.path.dirname(verified_jsonl_path)

    path_audit_csv = os.path.join(data_dir, "complete_audit_trail.csv")
    path_prisma_json = os.path.join(data_dir, "prisma_flow_summary.json")
    path_prisma_md = os.path.join(data_dir, "prisma_flow_report.md")
    path_export_csv = os.path.join(data_dir, "cleaned_metadata.csv")

    source_path = verified_jsonl_path if os.path.exists(verified_jsonl_path) else (
        ngram_filtered_path if os.path.exists(ngram_filtered_path) else (
            about_filtered_path if os.path.exists(about_filtered_path) else (
                type_filtered_path if os.path.exists(type_filtered_path) else raw_metadata_path
            )
        )
    )
    if not os.path.exists(source_path) and not os.path.exists(duckdb_path):
        st.warning("エクスポート対象データが存在しません。Step 1 でメタデータを取得してください。")
        st.stop()

    # DuckDBがあるか確認し、PRISMA統計を取得
    db = None
    prisma_stats = None
    manifest = get_acquisition_manifest(manifest_path)

    if os.path.exists(duckdb_path):
        try:
            db = DuckDBManager(db_path=duckdb_path)
            prisma_stats = db.get_prisma_flow_stats()
        except Exception:
            pass

    # =========================================================================
    # 1. 絞り込みプロセス統計プレビュー (PRISMA Metrics)
    # =========================================================================
    if prisma_stats and prisma_stats.get("total_records", 0) > 0:
        with st.container(border=True):
            st.markdown("#### 📊 系統的レビュー（PRISMA準拠）プロセス概要")
            tot = prisma_stats["total_records"]
            ad = prisma_stats["final_adopted"]
            disc = prisma_stats["final_discarded"]

            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            col_p1.metric("初期同定数 (SPARQL)", f"{tot:,} 件")
            col_p2.metric("Type除外数", f"{prisma_stats['type_discarded']:,} 件")
            col_p3.metric("ルール合格 (About/語彙)", f"{prisma_stats['rule_ok']:,} 件")
            col_p4.metric("最終採択数 (合格)", f"{ad:,} 件", delta=f"{ad/max(1, tot):.1%}")

            with st.expander("詳細な除外理由ランキング（上位10件）", expanded=False):
                if prisma_stats["top_drop_reasons"]:
                    for rank, (rsn, cnt) in enumerate(prisma_stats["top_drop_reasons"], 1):
                        st.markdown(f"**{rank}.** `{rsn}`: **{cnt:,} 件** ({cnt/max(1, disc):.1%})")
                else:
                    st.caption("除外理由集計データがありません。")

    st.write("---")

    # =========================================================================
    # 2. 一括エクスポート実行ボタン
    # =========================================================================
    if st.button("🚀 学術研究パッケージ（検索用JSON ＆ 全件追跡CSV ＆ PRISMAレポート）の一括生成・出力", type="primary", use_container_width=True):
        records = []
        viewer_records = []

        # A. DuckDBからの高速かつ完全来歴付き抽出
        if db and db.get_record_count() > 0:
            query = """
                SELECT 
                    id, 
                    title, 
                    description, 
                    coalesce(review_reasons, primary_reason, matched_reason, '全ルール通過') AS p_reason,
                    coalesce(adopted_stage, 'RULE') AS p_stage,
                    raw_json
                FROM metadata_records
                WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格';
            """
            rows = db.conn.execute(query).fetchall()
            for r in rows:
                item_id, title, desc, p_reason, p_stage, raw_j = r
                raw_data = json.loads(raw_j) if raw_j else {}

                provider = 'Japan Search'
                source = raw_data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                if isinstance(source, dict):
                    prov_val = source.get('schema:provider', '')
                    if prov_val:
                        provider = str(prov_val).split('/')[-1]

                genre = "古典資料/その他"
                t_desc = (str(title) + " " + str(desc)).lower()
                if any(k in t_desc for k in ["雅楽", "笙", "篳篥", "竜笛"]): genre = "雅楽"
                elif any(k in t_desc for k in ["謡", "能", "観世", "宝生"]): genre = "能楽/謡曲"
                elif any(k in t_desc for k in ["三味線", "長唄", "地歌", "義太夫"]): genre = "三味線音楽"
                elif any(k in t_desc for k in ["尺八", "琴古", "都山"]): genre = "尺八楽"
                elif any(k in t_desc for k in ["琵琶", "平曲"]): genre = "琵琶楽"

                image = raw_data.get('schema:image', '')
                if isinstance(image, list) and image: image = image[0]

                viewer_records.append({
                    "id": item_id,
                    "title": title or "無題資料",
                    "description": str(desc)[:300] if desc else "詳細記述なし",
                    "provider": provider,
                    "genre": genre,
                    "url": item_id,
                    "image": image if isinstance(image, str) else '',
                    "provenance": {
                        "stage": p_stage,
                        "reason": p_reason,
                        "confidence": "HIGH" if p_stage in ["RULE", "RULE_ABOUT", "RULE_NGRAM", "HUMAN"] else "MEDIUM"
                    }
                })

            # B. 完全追跡データ (Complete Audit Trail) のCSV書き出し
            db.export_complete_audit_trail_csv(path_audit_csv)

            # C. PRISMA レポート (Markdown & JSON) の出力
            if prisma_stats:
                with open(path_prisma_json, 'w', encoding='utf-8') as f:
                    json.dump(prisma_stats, f, ensure_ascii=False, indent=2)
                prisma_md_text = generate_prisma_markdown_report(prisma_stats, manifest)
                with open(path_prisma_md, 'w', encoding='utf-8') as f:
                    f.write(prisma_md_text)

        # フォールバック処理 (JSONLから直接パース)
        else:
            with open(source_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        label = data.get('rdfs:label', data.get('schema:name', 'No Title'))
                        title = label[0] if isinstance(label, list) and label else str(label)
                        desc_val = data.get('schema:description', '')
                        desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)
                        provider = 'Japan Search'
                        source = data.get('https://jpsearch.go.jp/term/property#sourceInfo', {})
                        if isinstance(source, dict):
                            provider = str(source.get('schema:provider', '')).split('/')[-1]

                        item_id = data.get('@id', data.get('id', ''))
                        p_reason = data.get("review_reasons", data.get("reason", "ルール合致"))
                        viewer_records.append({
                            "id": item_id,
                            "title": title,
                            "description": desc[:300] if desc else "詳細記述なし",
                            "provider": provider,
                            "genre": "古典資料/その他",
                            "url": item_id,
                            "provenance": {
                                "stage": "RULE",
                                "reason": p_reason,
                                "confidence": "HIGH"
                            }
                        })
                    except Exception:
                        continue

        # 検索ビューア用 JSON 保存
        safe_save_json(viewer_records, export_json_path)

        # クレンジング済み CSV 保存
        df_export = pd.DataFrame(viewer_records)
        df_export.to_csv(path_export_csv, index=False, encoding='utf-8-sig')

        st.success(f"🎉 学術パッケージの出力がすべて完了しました！全 {len(viewer_records):,} 件の確定資料を `{export_json_path}` および `{path_export_csv}` に生成しました。")

    if db:
        db.close()

    st.write("---")

    # =========================================================================
    # 3. 成果物ダウンロードパネル
    # =========================================================================
    st.subheader("📦 成果物 ＆ 再現性・監査パッケージのダウンロード")
    st.markdown("論文の付録（Supplementary Materials）や研究リポジトリ登録に必要なデータパッケージを個別または一括で取得できます。")

    st.markdown("##### 1. 資料データセット成果物")
    c_dl1, c_dl2, c_dl3 = st.columns(3)
    with c_dl1:
        if os.path.exists(export_json_path):
            with open(export_json_path, 'rb') as f:
                st.download_button(
                    label="scores_data.json のダウンロード (来歴付)",
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

    st.write("---")
    st.markdown("##### 2. 再現性・監査（Provenance & Audit）パッケージ")
    c_p1, c_p2, c_p3 = st.columns(3)

    with c_p1:
        if os.path.exists(path_audit_csv):
            with open(path_audit_csv, 'rb') as f:
                st.download_button(
                    label="📋 complete_audit_trail.csv (全件追跡)",
                    data=f,
                    file_name="complete_audit_trail.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.button("complete_audit_trail.csv (未出力)", disabled=True, use_container_width=True)

    with c_p2:
        if os.path.exists(path_prisma_md):
            with open(path_prisma_md, 'rb') as f:
                st.download_button(
                    label="📊 prisma_flow_report.md (PRISMAレポート)",
                    data=f,
                    file_name="prisma_flow_report.md",
                    mime="text/markdown",
                    use_container_width=True
                )
        else:
            st.button("prisma_flow_report.md (未出力)", disabled=True, use_container_width=True)

    with c_p3:
        if os.path.exists(manifest_path):
            with open(manifest_path, 'rb') as f:
                st.download_button(
                    label="⚙️ acquisition_manifest.json (取得レシピ)",
                    data=f,
                    file_name="acquisition_manifest.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.button("acquisition_manifest.json (未出力)", disabled=True, use_container_width=True)

