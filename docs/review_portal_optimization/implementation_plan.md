# 実装計画: Step 4 専門家査読ポータルの高速化・DuckDB化

## 1. 概要・背景
現行の「Step 4: 専門家査読ポータル」では、以下の4〜5個の巨大ファイルを毎フレームすべて読み直してメモリ上で全結合（マージ）している：
1. `raw_metadata.jsonl` (初期データ全件)
2. `about_filtered.jsonl`
3. `ngram_filtered.jsonl`
4. `type_filtered.jsonl`
5. `llm_judgments.jsonl`

さらに、数万件の全レコードに対してStreamlit上でPythonのリスト内包表記による文字列検索・ステータス絞り込みを毎操作ごとに実行しているため、数万件規模では画面表示やページ送りが著しくもたつく。

本改修では、先行して導入した **DuckDB** を査読ポータルにも全面適用し、**「サーバーサイド・ページネーション」** と **「高速SQLフィルタリング」** を導入することで、数万件あっても画面操作がミリ秒単位で完了する構造へ刷新する。

## 2. アーキテクチャ設計

### 2.1 テーブル構造の拡張 (`metadata_records`)
```sql
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS llm_target BOOLEAN DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS llm_reason VARCHAR DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS external_info VARCHAR DEFAULT NULL;
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS human_decision VARCHAR DEFAULT NULL; -- '合格', '除外', NULL
ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS review_reasons VARCHAR DEFAULT NULL;
```

### 2.2 変更ファイル一覧
- **拡張**:
  - `01_cleansing_studio/modules/duckdb_manager.py`: 査読用クエリ、LLM判定マージ、判定更新メソッドの追加
  - `01_cleansing_studio/views/step2d_review_view.py`: サーバーサイドページネーションへの移行
  - `01_cleansing_studio/test_pipeline.py`: 査読機能のテスト追加
  - `01_cleansing_studio/benchmark_filter.py`: 査読クエリ速度のベンチマーク追加
- **ドキュメント**:
  - `docs/review_portal_optimization/task.md`
  - `docs/review_portal_optimization/implementation_plan.md`
  - `docs/review_portal_optimization/walkthrough.md`
