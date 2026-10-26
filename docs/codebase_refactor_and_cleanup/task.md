# タスク進捗管理: コードベース整理・アーカイブ・保守性およびスケール可用性向上

## ステータス概要
- [x] 1. アーカイブ整理 (不要スクリプト・過去収集データ・不要ルールの退避) <!-- id: 1 -->
    - [x] `archive/` ディレクトリ構造の設計と作成 (`archive/scripts/`, `archive/rules/`, `archive/data/`) <!-- id: 1.1 -->
    - [x] `01_cleansing_studio/benchmark_filter.py` の退避 <!-- id: 1.2 -->
    - [x] 不要となった旧ルールファイル (`suffix_rules.json`, `ok_word_list.txt`, `ng_word_list.txt`) の退避 <!-- id: 1.3 -->
    - [x] 過去に収集された実メタデータ (`metadata_store.duckdb`, `raw_metadata.jsonl`, `complete_audit_trail.csv` 等) の `archive/data/` への安全退避 <!-- id: 1.4 -->
    - [x] クリーンな初期状態のワークスペースディレクトリおよびシンボリックリンク整合性の確認 <!-- id: 1.5 -->
- [x] 2. コードベース見直しと冗長性削除 (保守性向上) <!-- id: 2 -->
    - [x] `01_cleansing_studio/modules/rule_filter.py` の未参照関数削除 (`run_suffix_filter`, `extract_suffixes_from_jsonl` 等) <!-- id: 2.1 -->
    - [x] モジュール・インポートのクリーンアップと例外処理の整理 <!-- id: 2.2 -->
- [x] 3. 数万件規模のメタデータ処理に向けた軽量化・スケール可用性向上 <!-- id: 3 -->
    - [x] `01_cleansing_studio/views/step2c_llm_view.py`: 旧来のJSONL行ループ分割から DuckDB 高速エンジン (`apply_rules_fast` / `export_split_datasets`) への移行 <!-- id: 3.1 -->
    - [x] `01_cleansing_studio/views/step2a_about_view.py` & `step2b_ngram_view.py`: メモリ消費の抑制とDuckDB SQL集計の優先活用 <!-- id: 3.2 -->
    - [x] `01_cleansing_studio/modules/workspace_manager.py`: 初期データ空状態での堅牢なディレクトリ・DB自動生成 <!-- id: 3.3 -->
    - [x] `02_search_viewer`: データ未生成時の親切なガイダンス表示（白画面・エラー防止） <!-- id: 3.4 -->
- [x] 4. テストと動作検証 <!-- id: 4 -->
    - [x] `01_cleansing_studio/test_pipeline.py` にクリーン初期化・DuckDB高速分割等の検証を追加 <!-- id: 4.1 -->
    - [x] 全パイプラインテストの実行と全パス確認 <!-- id: 4.2 -->
    - [x] 検索ビューア (`02_search_viewer`) の動作確認 <!-- id: 4.3 -->
- [x] 5. README.md の刷新とウォークスルー作成 <!-- id: 5 -->
    - [x] `README.md` の包括的更新 (DuckDB, バックグラウンドワーカー, 来歴追跡・PRISMA, ワークスペース, アーカイブ運用) <!-- id: 5.1 -->
    - [x] `docs/codebase_refactor_and_cleanup/walkthrough.md` の作成 <!-- id: 5.2 -->
