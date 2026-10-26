# タスク進捗管理: Step 4 専門家査読ポータルの高速化・DuckDB化

## タスク一覧

- [x] **Phase 1: 設計と事前ベンチマーク**
  - [x] 現行方式（4ファイル全件マージ方式）の査読ロード時間・メモリ計測
  - [x] DuckDB査読スキーマおよびクエリ設計
- [x] **Phase 2: DuckDBManager の査読機能拡張**
  - [x] `sync_llm_judgments(llm_jsonl_path)`: LLM結果の一括統合
  - [x] `get_review_metrics()`: 査読統計メトリクスの超高速SQL集計
  - [x] `query_review_records(filter_type, search_query, page, page_size)`: サーバーサイド検索・ページネーション
  - [x] `set_human_decision(item_id, decision)`: 単一判定の即時DB更新
  - [x] `export_human_verified_data(output_path)`: 確定合格データの高速エクスポート
- [x] **Phase 3: 査読ビュー (`step2d_review_view.py`) の刷新**
  - [x] オンメモリ全件ループ・セッション巨大辞書を全廃
  - [x] サーバーサイドページネーション（1ページ分のみDOM描画）へのリファクタリング
  - [x] 既存JSONL方式への安全フォールバック確保
- [x] **Phase 4: テスト・ベンチマーク測定・ドキュメント作成**
  - [x] `test_pipeline.py` に査読ポータルのテスト追加・全件パス検証（全8工程パス）
  - [x] ベンチマーク測定（表示・検索速度 **33.3倍高速化**、メモリ **99.7%削減** を達成）
  - [x] `walkthrough.md` の作成と完了報告
