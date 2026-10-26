# 実装計画: メタデータ構築・絞り込みプロセスの再現性＆追跡可能性（Provenance & Audit）向上

## 1. 概要・背景
本システム（JPS-Refine Studio）は、学術研究成果（文化資源デジタルアーカイブ・論文・研究データ）として外部公開されることを目的としています。
学術研究において、データ抽出・精緻化パイプラインには以下の要件が不可欠です：
1. **再現性 (Reproducibility)**:
   どのような条件（SPARQLクエリ、検索語彙、NDC分類、正規表現、AIモデル設定）で初期メタデータプールが構築されたかを第三者が完全に再実行・検証できること。
2. **追跡可能性 (Traceability / Data Provenance)**:
   母集団の全レコードについて、「どの段階で、どのような理由で合格・除外されたのか」が1件単位で追跡できること。
3. **結果と過程の一体提示 (Integrated Presentation)**:
   絞り込み結果（合格データ）のみを切り離すのではなく、公開用ビューア上で各資料の「採択根拠」を明示し、かつ絞り込み過程全体（PRISMAフロー・除外統計）を一緒に提示・検証できること。
4. **追跡データの単独利用性 (Standalone Audit Trail)**:
   除外されたデータも含めた完全な追跡データセット（Audit Trail CSV）を単独で取り出し、査読者や利用者が独自の検証や二次利用を行えること。

---

## 2. アーキテクチャとデータ構造設計

### 2.1 データ取得マニフェスト (`data/acquisition_manifest.json`)
初期プール（Step 1）の構築レシピを保存する仕様：
- `dataset_name`: データセット名
- `created_at`: 取得開始〜完了タイムスタンプ
- `endpoint`: `https://jpsearch.go.jp/rdf/sparql/`
- `parameters`:
  - `keywords`: 検索語彙リスト
  - `target_ndc`: 包含NDC分類コード一覧
  - `exclude_ndc`: 除外NDC分類コード一覧
  - `title_regex`: タイトル正規表現パターン
  - `desc_regex`: 説明文正規表現パターン
  - `domain_definition`: ドメイン定義文
- `sparql_queries`: 生成・実行された全SPARQLクエリ（Part 1〜Part N）
- `metrics`:
  - `total_target_uris`: 取得URI数
  - `success_count`: メタデータ正常取得件数
  - `failed_count`: 取得失敗件数

### 2.2 DuckDB スキーマ拡張 (`metadata_records`)
`metadata_store.duckdb` のテーブルを以下のように拡張し、全工程の判定理由を1つの行に統合：
```sql
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS type_reason VARCHAR DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS about_reason VARCHAR DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS ngram_reason VARCHAR DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS adopted_stage VARCHAR DEFAULT NULL; -- 'RULE_ABOUT', 'RULE_NGRAM', 'LLM', 'HUMAN'
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS drop_stage VARCHAR DEFAULT NULL;    -- 'TYPE', 'RULE_ABOUT', 'RULE_NGRAM', 'LLM', 'HUMAN'
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS primary_reason VARCHAR DEFAULT NULL;
```

### 2.3 学術出力成果物パッケージ (Step 5)
1. **`scores_data.json` (検索用・来歴インライン化)**:
   各資料に以下を追加：
   ```json
   {
     "id": "https://jpsearch.go.jp/data/...",
     "title": "雅楽譜 ...",
     "provenance": {
       "stage": "RULE",
       "reason": "タイトル OK: 「雅楽」",
       "confidence": "HIGH"
     }
   }
   ```
2. **`complete_audit_trail.csv` (全件追跡データ)**:
   初期プールの全レコードを網羅したCSV：
   `id`, `title`, `final_decision` (ADOPTED / DISCARDED), `decision_stage`, `primary_reason`, `type_status`, `type_reason`, `about_status`, `about_reason`, `ngram_status`, `ngram_reason`, `llm_status`, `llm_reason`, `human_decision`, `review_reasons`
3. **`prisma_flow_summary.json` & `prisma_flow_report.md` (PRISMA準拠サマリー)**:
   - Identification（初期同定数）
   - Screening（Type除外数、About除外数、N-gram除外数）
   - Eligibility（LLM判定数、LLM除外数、査読修正数）
   - Included（最終採択数）
   - 除外理由別の上位ランキング

### 2.4 公開用検索ビューア（`02_search_viewer`）の拡張
- **個別資料表示**: カードおよび詳細モーダルに「🏷️ 採択根拠（Provenance Badge）」を美しく表示。
- **「📊 絞り込みプロセス（Methodology）」タブ新設**:
  - 初期検索条件（マニフェスト）の表示
  - PRISMAフロー図（MermaidまたはHTML/CSSステップカード）
  - 主な除外理由の内訳（家譜・画譜等の割合グラフ）
  - `complete_audit_trail.csv` および `acquisition_manifest.json` の直接ダウンロードリンク

---

## 3. 変更対象ファイル一覧

| ファイル | 役割と変更内容 |
| :--- | :--- |
| `01_cleansing_studio/modules/duckdb_manager.py` | 来歴追跡カラムの追加・マイグレーション、各ステージの判定理由記録メソッド、監査用エクスポート（Audit Trail CSV, PRISMAサマリー）の実装 |
| `01_cleansing_studio/modules/sparql_collector.py` | データ取得完了時のマニフェスト（`acquisition_manifest.json`）自動生成・保存 |
| `01_cleansing_studio/views/step1_fetch_view.py` | クエリ実行時のマニフェスト情報保持・連携 |
| `01_cleansing_studio/modules/rule_filter.py` | Step 2-A (Type) で除外されたレコードとマッチ理由のDuckDB同期対応 |
| `01_cleansing_studio/views/step2_type_view.py` | Type除外実行時のDuckDB来歴記録呼び出し |
| `01_cleansing_studio/views/step3_export_view.py` | 採択根拠付き `scores_data.json`、`complete_audit_trail.csv`、`prisma_flow_report.md` の一括出力UI |
| `02_search_viewer/index.html` | プロセスタブのUI骨格、採択根拠バッジ枠の追加 |
| `02_search_viewer/style.css` | プロセス表示・PRISMAフロー・採択根拠バッジ用のモダンCSSスタイル |
| `02_search_viewer/app.js` | 採択根拠のバッジ描画、プロセスタブの動的描画（マニフェスト・フローチャート・除外統計） |
| `01_cleansing_studio/test_pipeline.py` | 来歴追跡・マニフェスト生成・監査エクスポートの単体テスト追加 |

---

## 4. 検証・受け入れ基準
1. **Step 1 実行時**: `data/acquisition_manifest.json` が生成され、SPARQLクエリや検索条件が完全記録されること。
2. **Step 2〜4 実行時**: DuckDB上で除外・採択された全レコードの `drop_stage`, `primary_reason`, `adopted_stage` が正確に記録されること。
3. **Step 5 実行時**: 
   - `scores_data.json` に各レコードの `provenance` が含まれること。
   - `data/complete_audit_trail.csv` が初期全件分正しく出力されること。
   - `data/prisma_flow_summary.json` および `prisma_flow_report.md` に各ステップの通過・除外件数が整合性を持って集計されること。
4. **02_search_viewer 動作確認**:
   - 資料カード上で「採択根拠バッジ」が表示されること。
   - 「絞り込みプロセス」タブに切り替えた際、初期条件、PRISMAフロー、ダウンロードリンクが正常に表示されること。
5. **パイプラインテスト**: 全テストがパスすること。
