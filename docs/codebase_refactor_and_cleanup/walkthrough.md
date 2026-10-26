# ウォークスルー: スクリプト整理・アーカイブ・保守性およびスケール可用性向上

## 1. 作業の概要
本改修では、これまでに実施された多数の機能拡張（DuckDB高速エンジン、バックグラウンドワーカー、来歴追跡・PRISMA 2020、ワークスペース＆スナップショット管理等）を踏まえ、以下の整理・改善を実施しました：

1. **不要・古いスクリプトおよび過去収集データのアーカイブ退避**:
   - 一連の検証が完了した旧スクリプト、旧ルールファイル、および過去に収集された巨大実データ（約1.8GB）を `archive/` ディレクトリに安全に退避。
2. **コード全体の冗長性削除（保守性向上）**:
   - `01_cleansing_studio/modules/rule_filter.py` 内の未参照関数（旧接尾辞処理）を安全に削除。
3. **数万件規模のメタデータを扱うためのスケール可用性・動作軽量化**:
   - `step2c_llm_view.py` におけるデータ仕分け処理を、旧来の行ループ（`split_dataset_by_rules`）から DuckDB 高速エンジン（`apply_rules_fast` / `export_split_datasets`）へ移行。
   - `duckdb_manager.py` の `export_split_datasets` の戻り値を拡張し、分割結果の件数（OK, NG, GREY）を即座に取得可能に改善。
   - `02_search_viewer` において、データ未エクスポート時にもエラーにならず、直感的なアクション案内を表示するガイダンスUIを導入。
4. **慎重なテストと動作検証**:
   - `test_pipeline.py` にクリーン環境初期化およびDuckDB高速仕分けの単体・結合テスト（Test 11）を追加し、全11テストが正常に合格することを確認。
5. **最新機能とアーキテクチャを踏まえた `README.md` の包括的改訂**。

---

## 2. 変更・アーカイブファイル一覧

### 2.1 アーカイブ退避 (`archive/`)

| 移動元 | 退避先 | 内容・理由 |
| :--- | :--- | :--- |
| `01_cleansing_studio/benchmark_filter.py` | `archive/scripts/benchmark_filter.py` | DuckDB比較ベンチマーク検証完了スクリプト |
| `01_cleansing_studio/rules/suffix_rules.json` | `archive/rules/suffix_rules.json` | 旧接尾辞ルール（`ngram_rules.json` に統合済み） |
| `01_cleansing_studio/rules/ok_word_list.txt` | `archive/rules/ok_word_list.txt` | 初期単語リスト（`ngram_rules.json` に統合済み） |
| `01_cleansing_studio/rules/ng_word_list.txt` | `archive/rules/ng_word_list.txt` | 初期単語リスト（`ngram_rules.json` に統合済み） |
| `data/workspaces/gagaku_default/data/*` (1.8GB) | `archive/data/gagaku_initial_run/` | 過去に収集された実メタデータ資産（DuckDB, 生JSONL, 監査CSV等） |
| `02_search_viewer/scores_data.json` (退避コピー) | `archive/data/gagaku_initial_run/scores_data.json` | 過去に出力された公開用データセット |

### 2.2 ソースコード修正

| ファイル | 変更区分 | 主な内容 |
| :--- | :--- | :--- |
| `01_cleansing_studio/modules/rule_filter.py` | **改修** | 未使用関数 `extract_suffixes_from_jsonl`、`run_suffix_filter` の削除 |
| `01_cleansing_studio/modules/duckdb_manager.py` | **改修** | `export_split_datasets` の戻り値として `(ok_cnt, ng_cnt, grey_cnt)` を返すよう改善 |
| `01_cleansing_studio/views/step2c_llm_view.py` | **改修** | DuckDBManager を優先活用し、数万件規模のルール仕分けをミリ秒〜数秒で完了するよう高速化 |
| `02_search_viewer/app.js` | **改修** | データ未エクスポート時の親切なガイダンスカード表示（白画面・エラー防止） |
| `01_cleansing_studio/test_pipeline.py` | **改修** | クリーン環境初期化とDuckDB高速分割を検証する `test_clean_environment_and_duckdb_split()` (Test 11) の追加 |
| `README.md` | **刷新** | DuckDB、バックグラウンドワーカー、来歴追跡・PRISMA、ワークスペース、アーカイブ運用等を網羅した最新版へ刷新 |

---

## 3. テスト検証結果

パイプライン総合テスト (`01_cleansing_studio/test_pipeline.py`) を実行し、全11テストすべてが正常通過（Exit Code: 0）しました：

```text
--------------------------------------------------
  Japan Search Enhanced Pipeline & Module Unit Tests
--------------------------------------------------
=== [Test 1] Fast LLM Context Suggestion Test ===
[OK] Fast Suggestion Response Time: 0.00 秒
[OK] Contextual Base Suggestion Response Time: 0.00 秒
=== [Test 2] LLM Query Expansion Test ===
[OK] Theme: 日本の古典籍における楽譜資料
[OK] Keywords: ['日本', '古典籍', '楽譜']
=== [Test 3] SPARQL Query Generation Test ===
[OK] Generated 4 query patterns.
=== [Test 4] Schema:About Extraction & Filter Test ===
[OK] Extracted about values: ['ndc#760', '雅楽', '日本音楽', '地図']
[OK] About Filter: passed=1, disc=1
=== [Test 5] N-Gram Extraction & Filter Test ===
[OK] Extracted Bi-gram top items count: 6
[OK] N-Gram Filter: passed=2, disc=1
=== [Test 6] Review Portal & LLM Response Parser Test ===
[OK] LLM Classifier JSON Parser test passed.
[OK] Review portal merged data loaded cleanly without TypeError.
[OK] Saved human verified records count: 1
=== [Test 7] Symbol Cleaning & Multithreaded LLM Classifier Test ===
[OK] Clean symbol N-Gram extraction verified. Bi-grams: []
[OK] Multithreaded LLM classifier finished successfully. (acc=0, rej=0, unk=3)
=== [Test 8] DuckDB High-Speed Engine Unit Test ===
[OK] DuckDB imported 4 records.
[OK] DuckDB apply_rules_fast result: {'ok': 1, 'ng': 2, 'grey': 1, 'total': 4}
[OK] DuckDB review metrics verified: {'total': 4, 'pass_cnt': 1, 'reject_cnt': 3, 'override_cnt': 0, 'null_cnt': 0}
[OK] DuckDB manual override verified: override_cnt=1
=== [Test 9] SPARQL Fetch Job Status & Resume Integration Test ===
[OK] Initial job status: IDLE
[OK] Process alive check: PID is alive.
[OK] Resume complete: All 4 records safely retained without duplicate.
=== [Test 10] Provenance & Audit Trail Integration Test ===
[OK] Acquisition manifest save & load verified.
[OK] Type filter fast & provenance record verified: {'total': 4, 'passed': 3, 'discarded': 1}
[OK] Rule filter fast & provenance record verified: {'ok': 1, 'ng': 2, 'grey': 1, 'total': 4}
[OK] PRISMA flow statistics verified: OK=1, Disc=3
[OK] Complete Audit Trail CSV exported and verified with all 4 records.
=== [Test 10] Workspace and Snapshot Management Test ===
[OK] WorkspaceManager initialized with default workspace: gagaku_default
[OK] New workspace created: ukiyoe_test
[OK] Snapshot saved successfully: snap_20261026_115939
[OK] Snapshot restored successfully! Decisions rolled back in DuckDB.
[OK] Recipe bundle exported: 403 bytes
[OK] Recipe bundle imported successfully as new workspace: imported_study
[OK] Workspace deletion verified. Default workspace remains protected.
=== [Test 11] Clean Environment & DuckDB Split Optimization Test ===
[OK] Workspace paths safely resolved in clean state: /Users/shint/Desktop/JPS_Refine_Studio/data/workspaces/gagaku_default
[OK] DuckDB apply_rules_fast & export_split_datasets verified: OK=1, NG=2, Grey=1

==================================================
 SUCCESS: All enhanced pipeline & module tests passed!
==================================================
```

---

## 4. 保守性と今後の運用

1. **データ資産の復元が必要な場合**:
   - `archive/data/gagaku_initial_run/` 内の各ファイルを `data/workspaces/gagaku_default/data/` へコピーするだけで、過去の雅楽実データセット（15万件のDuckDBおよび生メタデータ）を即座に再稼働できます。
2. **新規テーマ（浮世絵・能楽・古地図等）の研究開始時**:
   - スタジオサイドバーまたは `workspace_view` から新規ワークスペースを作成するだけで、独立した作業空間とクリーンなルールテンプレートが自動生成されます。
3. **数万件規模の運用時**:
   - 全ての主要処理（Type除外、About判定、N-gram判定、LLM仕分け、専門家査読、成果物エクスポート）が DuckDB 高速エンジンに統合されており、メモリ枯渇やブラウザフリーズを起こすことなく安定して動作します。
