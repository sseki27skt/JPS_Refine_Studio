# タスク管理: Step 1 Japan Search メタデータ取得最適化

## 概要
Japan Search からの数万件規模のメタデータ（SPARQL SELECT/CONSTRUCT）収集において、
ブラウザを閉じても安全に作業が継続でき、中断・再開や適応型レート制御を備えた堅牢なバックグラウンド処理基盤を構築する。

---

## タスクリスト

- [x] **1. 設計ドキュメント作成**
  - [x] `.gitignore` の更新（`!docs/sparql_fetch_optimization/`）
  - [x] `task.md` の作成
  - [x] `implementation_plan.md` の作成

- [x] **2. コアモジュール改修 (`sparql_collector.py`)**
  - [x] 中断・再開（レジューム機能: 既存取得URIの差分スキップ＆追記モード）
  - [x] 適応型レート制御（Adaptive Batch Sizing: サーバー負荷検知で5〜30件へ動的伸縮）
  - [x] 状態管理ファイル（`data/fetch_job_status.json`）の定期更新機能
  - [x] バックグラウンドワーカー用関数の実装

- [x] **3. バックグラウンドワーカー (`run_fetch_worker.py`)**
  - [x] CLI/バックグラウンドプロセス実行スクリプトの作成
  - [x] PID管理・シグナルハンドリング（安全な停止）
  - [x] DuckDB への自動同期

- [x] **4. WebUI 統合 (`step1_fetch_view.py`)**
  - [x] ジョブステータス監視＆グローバル案内バナー（実行中・完了時の一目認識）
  - [x] 二重起動防止ロック（実行中のボタン無効化）
  - [x] バックグラウンド実行切り替えスイッチ
  - [x] 安全な一時停止（Stop）ボタン
  - [x] 完了時の「Step 2へ進む」導線

- [x] **5. テスト・検証およびウォークスルー作成**
  - [x] レジューム機能（中断・再開）の単体テスト
  - [x] 適応型レート制御の単体テスト
  - [x] `test_pipeline.py` への統合と全パス確認
  - [x] `walkthrough.md` の作成
