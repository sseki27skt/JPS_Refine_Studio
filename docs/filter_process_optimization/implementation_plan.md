# 実装計画: フィルタリングプロセスの高速化・DuckDB化

## 1. 概要・背景
Japan Searchから得られる数万件単位の大規模文化資源メタデータにおいて、従来の「多重JSONL逐次ファイルI/O ＋ Pythonのforループによる全件スキャン」方式では、以下の深刻なパフォーマンス低下が発生していた：
1. **Aboutキーワード頻度集計**: 数万件のJSONパースとCounter集計による激しいCPU・I/O負荷
2. **N-gram抽出・頻度集計**: 巨大文字列パースと多重N-gram生成によるメモリ消費
3. **ルール適用・データ分割**: ステップごとに巨大なJSONLファイルを新規書き出しするI/Oオーバーヘッド

これらを解決するため、列指向組み込みデータベース **DuckDB** を導入し、データ集計・フィルタリング処理をC++並列エンジンに移行する。

## 2. アーキテクチャ設計

### 2.1 データベース構造 (`jps_refine.duckdb`)
テーブル名: `metadata_records`
- `id` (VARCHAR PRIMARY KEY): 資料URI (`@id`)
- `title` (VARCHAR): タイトル (`rdfs:label` / `schema:name`)
- `description` (VARCHAR): 説明文 (`schema:description`)
- `about_list` (VARCHAR[]): 抽出済み `schema:about` キーワード配列
- `type_list` (VARCHAR[]): `rdf:type` 配列
- `raw_json` (JSON): 生メタデータ全体
- `type_status` (VARCHAR): 'OK', 'NG', NULL
- `about_status` (VARCHAR): 'OK', 'NG', NULL
- `ngram_status` (VARCHAR): 'OK', 'NG', NULL
- `llm_status` (VARCHAR): 'OK', 'NG', 'UNKNOWN', NULL
- `review_status` (VARCHAR): 'OK', 'NG', NULL (手動オーバーライド)
- `final_decision` (VARCHAR): 'OK', 'NG', 'GREY', NULL

### 2.2 変更ファイル一覧
- **新規作成**:
  - `01_cleansing_studio/modules/duckdb_manager.py`: DuckDB接続、インポート、集計・フラグ更新クエリ
  - `01_cleansing_studio/benchmark_filter.py`: 処理速度・メモリのベンチマーク測定スクリプト
- **機能拡張**:
  - `01_cleansing_studio/modules/rule_filter.py`: DuckDB利用可能時の高速About抽出・ルール適用処理
  - `01_cleansing_studio/modules/ngram_filter.py`: DuckDB利用可能時の高速N-gram抽出・ルール適用処理
  - `requirements.txt`: `duckdb` の追加

## 3. ベンチマーク検証項目
1. **Aboutキーワード頻度集計速度 (秒)**
2. **N-gram抽出・頻度集計速度 (秒)**
3. **ルール適用によるデータ3分割（OK / NG / Grey）速度 (秒)**
4. **メモリ使用量 (MB)**
5. **判定結果の整合性チェック**: 既存のPythonロジックの判定結果とDuckDBの判定結果が完全一致すること
