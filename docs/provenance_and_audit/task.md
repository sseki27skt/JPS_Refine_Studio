# タスク進捗管理: メタデータ構築・絞り込みプロセスの再現性＆追跡可能性（Provenance & Audit）向上

## タスク一覧

- [x] **Phase 1: 記録スキーマとデータ構造の設計**
  - [x] `docs/provenance_and_audit/implementation_plan.md` の作成・確定
  - [x] DuckDB `metadata_records` テーブルの来歴追跡スキーマ拡張（`type_reason`, `about_reason`, `ngram_reason`, `adopted_stage`, `drop_stage`, `primary_reason`）
  - [x] マニフェスト（`acquisition_manifest.json`）の仕様確定

- [x] **Phase 2: 初期メタデータプール取得条件の完全記録（Step 1）**
  - [x] `01_cleansing_studio/modules/sparql_collector.py` / `views/step1_fetch_view.py` の改修
  - [x] SPARQLクエリ全文、検索キーワード、包含/除外NDC、正規表現、タイムスタンプ、取得統計のマニフェスト保存処理の実装
  - [x] 初回バルクインポート時のDuckDBへの初期来歴メタデータ投入

- [x] **Phase 3: 段階的フィルタリング判定理由の完全追跡（Step 2 〜 Step 4）**
  - [x] Step 2-A (Type): `apply_type_filter` および `step2_type_view.py` で除外理由（マッチした `rdf:type`）をDuckDBへ記録
  - [x] Step 2-B (About) & Step 2-C (N-gram): `apply_rules_fast` でマッチした具体ルール・理由をレコード単位で保持
  - [x] Step 3 (LLM): LLM推論結果・判定理由（`llm_reason`）・外部典拠（`external_info`）の完全同期
  - [x] Step 4 (Review): 専門家による手動オーバーライド理由（`human_decision`, `review_reasons`）の記録

- [x] **Phase 4: 学術成果物出力パッケージの拡充（Step 5）**
  - [x] `01_cleansing_studio/views/step3_export_view.py` の改修
  - [x] ① 検索用データ `scores_data.json` への採択根拠（`provenance`）埋め込み
  - [x] ② 全件追跡データ `complete_audit_trail.csv` の一括出力機能
  - [x] ③ 系統的レビュー標準（PRISMA準拠）フロー集計 `prisma_flow_summary.json` / `prisma_flow_report.md` の自動生成

- [x] **Phase 5: 公開用検索ビューア（02_search_viewer）での結果・過程の一体提示**
  - [x] `02_search_viewer/index.html` に「絞り込みプロセス（Provenance）」タブのUI構造を追加
  - [x] `02_search_viewer/style.css` にプロセス可視化スタイル・採択根拠バッジ用デザインを追加
  - [x] `02_search_viewer/app.js` に各カードでの採択根拠表示およびプロセスタブのレンダリング（PRISMAフロー・除外統計グラフ）を実装

- [x] **Phase 6: 検証・テストとドキュメント**
  - [x] パイプライン総合テスト（`test_pipeline.py`）への追跡機能テスト追加と実行確認
  - [x] `docs/provenance_and_audit/walkthrough.md` の作成
  - [x] ユーザーへの完了報告
