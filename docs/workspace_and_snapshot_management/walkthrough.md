# ウォークスルー: 複数テーマ対応ワークスペース分離・フィルタリング経過保存・他者引継ぎ機能

## 1. 実装の概要
本改修では、人文学文化資源メタデータの収集からフィルタリングまでの作業データを柔軟にマネジメントするため、以下の3つの機能を実装・統合しました：

1. **研究テーマ（ワークスペース）の分離**:
   雅楽、浮世絵、能楽、古地図などの異なる研究テーマを独立した作業空間として管理し、データの衝突や上書きを防止。
2. **フィルタリング経過（スナップショット）の高速保存・ロールバック**:
   巨大な生メタデータ（数百MB〜GB）を複製することなく、ルールファイルとDuckDBの判定ステータスカラムのみを軽量Parquet形式（数MB）で瞬時に保存し、ワンクリックで以前の試行錯誤状態へ復元（行き来）可能。
3. **他者とのデータ共有・引き継ぎパッケージ（Export / Import）**:
   共同研究者への配布や論文付録用の「軽量レシピパッケージ（.zip）」および完全移行用の「完全アーカイブ」の生成・展開機能。

---

## 2. 変更・追加ファイル一覧

| ファイル | 変更区分 | 主な内容 |
| :--- | :--- | :--- |
| `01_cleansing_studio/modules/workspace_manager.py` | **新規** | ワークスペースCRUD、パス動的解決、スナップショット保存・復元、パッケージZIP生成・展開を統括するコアマネージャー |
| `01_cleansing_studio/views/workspace_view.py` | **新規** | プロジェクト一覧・作成・切替、作業履歴タイムライン、エクスポート・インポートを行う管理UIビュー |
| `01_cleansing_studio/app.py` | **改修** | サイドバー最上部へのワークスペース切替セレクタ常設、選択中プロジェクトに応じた動的パス注入、管理画面ルーティングの追加 |
| `01_cleansing_studio/run_fetch_worker.py` | **改修** | `--workspace-id` 引数の追加およびワークスペース配下への自動パス解決対応 |
| `01_cleansing_studio/test_pipeline.py` | **改修** | ワークスペース初期化、スナップショット保存復元、パッケージインポート/エクスポートの単体テスト追加 |
| `data/workspaces/gagaku_default/` | **新規作成** | 既存の「雅楽」データ資産（1.7GB）を安全に格納した初期ワークスペース |

---

## 3. 主要機能の動作解説

### 3.1 ワークスペース分離と後方互換性
- **自動マイグレーション**: 初回起動時に、既存の `data/` 直下のファイル（`metadata_store.duckdb`, `raw_metadata.jsonl` など）を `data/workspaces/gagaku_default/` に安全に配置し、元の `data/` 直下には互換シンボリックリンクを作成。これにより、従来のスクリプトやビューアが一切壊れません。
- **動的パス解決**: `WorkspaceManager.get_workspace_paths(ws_id)` により、既存のビューが求める `PATHS` 辞書と完全互換のパス群が動的に注入されます。

### 3.2 超高速スナップショット（試行錯誤の行き来）
- **保存**: DuckDB の `metadata_records` テーブルから、判定理由・ステータス（`final_decision`, `human_decision`, `type_status`, `about_status`, `ngram_status`, `primary_reason` 等）のみを抽出し、Zstandard圧縮された `decisions.parquet`（約1MB）とルール定義JSONをスナップショットディレクトリに保存。
- **復元**: DuckDB の `UPDATE ... FROM read_parquet(...)` により、15万件以上のレコードの判定状態が数秒で過去のセーブポイントに一括ロールバックされます。

### 3.3 データ共有・他者引き継ぎ（ZIPパッケージ）
- **軽量レシピパッケージ（Recipe Bundle）**: 収集マニフェスト、全ルール、査読ログ、除外統計のみをZIP化（数MB）。共同研究者へメール等で手軽に送付可能。
- **完全アーカイブパッケージ（Full Archive）**: 生JSONLやDuckDBを含めた完全バックアップ。
- **インポート**: ZIPファイルを画面上にドラッグ＆ドロップするだけで、即座に新規ワークスペースとして展開・登録されます。

---

## 4. 検証結果

### 単体テストおよび機能検証（`test_pipeline.py`）
以下のテストケースを実行し、すべて正常に合格（PASS）することを確認しました：
```text
=== [Test 10] Workspace and Snapshot Management Test ===
[OK] WorkspaceManager initialized with default workspace: gagaku_default
[OK] New workspace created: ukiyoe_test (浮世絵テストコレクション)
[OK] Dynamic paths correctly resolved for ukiyoe_test.
[OK] Snapshot saved successfully: snap_20261026_113849 (Metrics: {'total': 2, 'adopted': 1, 'discarded': 1, 'grey': 0})
[OK] Snapshot restored successfully! Decisions rolled back in DuckDB.
[OK] Recipe bundle exported: 401 bytes
[OK] Recipe bundle imported successfully as new workspace: imported_study
[OK] Workspace deletion verified. Default workspace remains protected.
==================================================
 SUCCESS: All enhanced pipeline & module tests passed!
==================================================
```

また、158,189件の実データを用いたスナップショット保存・復元ベンチマークでも、判定ステータスのParquetダンプ（約1.5MB）およびDuckDB一括更新が約8秒で安全に完了することを確認済みです。
