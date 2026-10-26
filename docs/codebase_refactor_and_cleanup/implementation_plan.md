# 実装計画: コードベース整理・アーカイブ・保守性およびスケール可用性向上

## 1. 背景と目的
これまでの開発で、以下の多数の高度な機能が拡張されてきました：
- DuckDB を中核とする高速フィルタリング＆集計エンジン
- バックグラウンド非同期ワーカー＆自動レジューム（進捗保存）
- PRISMA 2020 準拠の来歴追跡 (Provenance) と完全監査証跡 (Complete Audit Trail CSV)
- 複数テーマ対応ワークスペース分離と軽量スナップショット（Parquet差分保存・ロールバック）
- 検索ビューア (`02_search_viewer`) での来歴・PRISMAフロー一体表示

本改修では、これらの機能拡張を踏まえて：
1. **過去収集データや使われなくなったスクリプトを `archive/` に退避・整理**し、プロジェクトルートをクリーンにする。
2. **冗長コード（使われなくなった接尾辞関数や古いスクリプト）を削除・修正**し、保守性を向上させる。
3. **数万件規模のメタデータをスムーズに処理できるよう、未だ残る旧来のPythonループ処理を DuckDB エンジンへ移行・最適化**する。
4. **テストを慎重に行いながら進め、全機能が正常に動作することを確認**する。
5. **最新のアーキテクチャ・機能を反映した `README.md` を全面的に刷新**する。

---

## 2. 変更・移動計画

### 2.1 アーカイブ対象
- `archive/scripts/`:
  - `01_cleansing_studio/benchmark_filter.py`: DuckDB導入時の比較ベンチマークスクリプト
- `archive/rules/`:
  - `01_cleansing_studio/rules/suffix_rules.json`: 旧接尾辞ルール（`ngram_rules.json` に統合済み）
  - `01_cleansing_studio/rules/ok_word_list.txt`, `ng_word_list.txt`: 旧テキスト単語リスト（`ngram_rules.json` に統合済み）
- `archive/data/gagaku_initial_run/`:
  - 雅楽の実データ資産（`metadata_store.duckdb` (1.28GB), `raw_metadata.jsonl` (568MB), `complete_audit_trail.csv` (21MB), `target_uris.csv` (8.6MB), `benchmark_sample_10k.jsonl`, マニフェスト・パラメータ・ステータス等）
  - ※退避後、ワークスペース初期状態でもアプリが破綻なく起動し、新規収集やテストが安全に行えるよう整備。

### 2.2 コード最適化対象
- `01_cleansing_studio/modules/rule_filter.py`:
  - 未使用の `run_suffix_filter`、`extract_suffixes_from_jsonl` を削除。
- `01_cleansing_studio/views/step2c_llm_view.py`:
  - `split_dataset_by_rules`（巨大JSONL行ループ）を DuckDBManager の `apply_rules_fast` と `export_split_datasets` に切り替え、数万件規模の仕分けをミリ秒〜数秒で完了可能に高速化。
- `01_cleansing_studio/views/step2a_about_view.py` & `step2b_ngram_view.py`:
  - DuckDB が利用可能な場合は DuckDB SQL 集計を優先し、Pythonメモリへの巨大リスト展開を抑制。
- `01_cleansing_studio/modules/workspace_manager.py`:
  - 初期データ空状態での安全な動作保証。
- `02_search_viewer/index.html` & `app.js`:
  - `scores_data.json` が未生成または空の場合に「データ未エクスポート」のガイダンスを表示し、JSエラーや画面崩れを防止。

### 2.3 テスト計画
- `01_cleansing_studio/test_pipeline.py`:
  - 既存の全テストケースに加え、クリーンな環境初期化やDuckDB高速分割のテストを追加・検証。
- 実行コマンド: `.venv/bin/python3 01_cleansing_studio/test_pipeline.py`

### 2.4 ドキュメント刷新
- `README.md`:
  - 新機能（DuckDB、バックグラウンドワーカー、来歴追跡・PRISMA、ワークスペース・スナップショット、アーカイブ構造）を反映。
  - 最新のディレクトリ構成、セットアップ、運用手順を網羅。
