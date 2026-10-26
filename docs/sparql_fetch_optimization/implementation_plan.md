# 実装計画: Step 1 Japan Search メタデータ取得最適化

## 1. 背景と課題
- **課題1（UI同期ブロックとブラウザ離脱不可）**: 
  従来のメタデータ取得はStreamlitのUIスレッド上で同期的に実行されていたため、数千〜数万件の取得に10分〜数時間かかる間、ブラウザタブを閉じたりリロードすると処理が停止または切断される恐れがあった。
- **課題2（中断・再開ができない）**:
  途中で通信エラーやPCスリープ等で中断すると、出力ファイルが上書き（`mode='w'`）される仕様のため、最初からやり直しになっていた。
- **課題3（固定バッチによる非効率とサーバー負荷リスク）**:
  固定バッチサイズ（10件）で取得していたため、サーバーが空いている時は取得が遅く、負荷が高い時は504 Gateway Timeoutが頻発する原因になっていた。
- **課題4（人間のミス防止）**:
  「裏で動いていることを忘れてしまう」「二重起動してしまう」「終わったかどうかわからない」といった人間側の運用エラーを防ぐ仕組みが必要。OSネイティブ通知（osascript等）は権限トラブルがあるため、WebUIと状態管理ファイルのみで完全に制御する。

---

## 2. アーキテクチャ設計

### 2.1 状態管理ファイル (`data/fetch_job_status.json`)
バックグラウンドプロセスとWebUIを疎結合に同期するJSONファイル。
```json
{
  "pid": 12345,
  "status": "RUNNING",        // "IDLE", "RUNNING", "COMPLETED", "FAILED", "STOPPED"
  "stage": "build_metadata",  // "collect_uris", "build_metadata", "repair"
  "total_target": 5000,
  "processed_count": 1820,
  "current_batch_size": 20,
  "started_at": "2026-10-25 12:45:00",
  "updated_at": "2026-10-25 12:48:30",
  "eta_seconds": 320,
  "error_message": null
}
```

### 2.2 中断・再開（レジューム）機能
- `build_metadata_for_uris(..., resume=True)`
- 既存の `raw_metadata.jsonl` から取得済みURIの集合 `existing_uris` を読み出し。
- 未取得URI `pending_uris = [u for u in target_uris if u not in existing_uris]` を抽出。
- 追記モード（`open(..., 'a')`）で未取得分のみを取得・書き込み。
- 取得完了したレコードは逐次、またはバッチ単位でDuckDBManagerにも投入可能に。

### 2.3 適応型レート制御（Adaptive Batch Sizing）
- 初期バッチ: 10件
- 連続成功（200 OK かつ レスポンス時間 < 2.5s）が2回: `batch_size = min(max_limit, batch_size + 5)` (最大 30〜50件)
- 504/503/タイムアウト検知時: `batch_size = max(2, batch_size // 2)` に即時縮小し、クールダウン待機。

### 2.4 バックグラウンドワーカー (`run_fetch_worker.py`)
- `python run_fetch_worker.py --target-uris data/target_uris.csv --output-jsonl data/raw_metadata.jsonl`
- Streamlitからは `subprocess.Popen` で非同期起動。
- PIDの生死チェック（`os.kill(pid, 0)`）で異常終了時もステータスを自動是正。

### 2.5 WebUI (`step1_fetch_view.py`) の制御
- 画面読み込み時に `fetch_job_status.json` を確認。
- `RUNNING`: 「バックグラウンド取得中」バナー、進捗バー、推定残り時間表示。「実行」ボタン無効化（二重起動防止）、「停止」ボタン提供。
- `COMPLETED`: 「✅ 取得完了」バナー ＆「Step 2へ進む」ボタン表示。
- `IDLE` / `STOPPED`: 差分再開オプションと通常開始ボタン。

---

## 3. 変更対象ファイル一覧
1. `.gitignore`: `!docs/sparql_fetch_optimization/` 追加（完了）
2. `01_cleansing_studio/modules/sparql_collector.py`:
   - レジューム機能（差分URI検出 ＆ 追記書き込み）
   - 適応型レート制御（Adaptive Batch Sizing）
   - 状態管理ファイル連携（`update_job_status`, `get_job_status`）
3. `01_cleansing_studio/run_fetch_worker.py` (新規):
   - バックグラウンド実行エントリーポイント
4. `01_cleansing_studio/views/step1_fetch_view.py`:
   - バックグラウンドプロセス起動 ＆ 状態監視UI
   - 二重起動防止ロック ＆ 完了バナー
5. `01_cleansing_studio/test_pipeline.py`:
   - レジュームおよび適応型バッチの単体テスト追加
