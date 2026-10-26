# 実装計画: 複数テーマ対応ワークスペース分離・フィルタリング経過保存・他者引継ぎ機能

## 1. 概要・背景
本システム（JPS-Refine Studio）は、人文学文化資源メタデータの収集から精緻化（フィルタリング・AI判定・専門家査読）までを一貫して行う研究プラットフォームです。

現状の実装では、固定パス（ルート直下の `data/` および `01_cleansing_studio/rules/`）に全データが保存されており、以下の運用上の課題が存在します：
1. **複数研究テーマの並行進行ができない**:
   「雅楽」以外のテーマ（浮世絵、能楽、古地図など）を扱おうとすると、既存の生データやDuckDB、ルールファイルが上書きされてしまう。
2. **フィルタリング試行錯誤の行き来（非線形探索）ができない**:
   ルール（About語彙やN-gram閾値）を試行錯誤する際、途中の状態を保存・ロールバックできないため、安全な比較実験が行えない。
3. **他者とのデータ引き継ぎ・共同作業が困難**:
   共同研究者間で作業データを共有・引き継ぐためのポータブルなエクスポート/インポート機能がない。

本計画では、既存のコード資産を最大限に活かしつつ、**「大容量の母集団データ」**と**「軽量なルール・判定差分」**を分離した**3層構造のデータマネジメント基盤**を構築します。

---

## 2. アーキテクチャとデータ構造設計

### 2.1 ディレクトリ構造とワークスペース分離 (Layer 1)
プロジェクトルート配下に `data/workspaces/` を新設し、テーマごとに独立した作業ディレクトリをカプセル化します。

```text
data/
└── workspaces/
    ├── gagaku_default/                   <-- 既存データを自動移行・登録
    │   ├── workspace_meta.json           <-- ワークスペース情報 (ID, 名称, 作成日時, 説明)
    │   ├── acquisition_manifest.json     <-- 収集レシピ (SPARQL, 検索条件, 統計)
    │   ├── current_fetch_params.json     <-- 検索パラメータ
    │   ├── target_uris.csv               <-- 取得対象URI
    │   ├── raw_metadata.jsonl            <-- 生メタデータ (数百MB)
    │   ├── metadata_store.duckdb         <-- DuckDBデータベース (約1GB)
    │   ├── fetch_job_status.json         <-- バックグラウンドジョブ状況
    │   ├── rules/                        <-- ワークスペース固有のルール群
    │   │   ├── type_rules.json
    │   │   ├── about_rules.json
    │   │   ├── ngram_rules.json
    │   │   ├── ok_word_list.txt
    │   │   └── ng_word_list.txt
    │   ├── snapshots/                    <-- フィルタリング経過 (Layer 2)
    │   │   └── {snapshot_id}/
    │   │       ├── snapshot_meta.json    <-- 作成日時, メモ, PRISMA件数サマリー
    │   │       ├── rules/                <-- その時点のルール一式
    │   │       └── decisions.parquet     <-- 判定結果カラムの差分 (数MB)
    │   └── exports/                      <-- 最終成果物
    │       ├── scores_data.json
    │       ├── complete_audit_trail.csv
    │       └── prisma_flow_summary.json
    └── ukiyoe_collection/                <-- 別テーマのワークスペース
        └── ...
```

### 2.2 フィルタリング経過の超高速保存・復元 (Layer 2)
巨大な `raw_metadata.jsonl` やDuckDB全体を複製するとディスクが逼迫するため、**「ルール設定ファイル群」＋「DuckDBの判定カラムのみ」**をスナップショットとして保存します。

* **保存対象カラム**:
  `id`, `type_status`, `type_reason`, `about_status`, `about_reason`, `ngram_status`, `ngram_reason`, `llm_status`, `llm_reason`, `final_decision`, `human_decision`, `review_reasons`, `adopted_stage`, `drop_stage`, `primary_reason`
* **保存形式**: Apache Parquet 形式（数万件規模でも 2〜5MB 程度に圧縮され、ディスクを圧迫しません）。
* **復元（ロールバック）処理**:
  1. スナップショットの `rules/` をワークスペースの `rules/` へ上書き展開。
  2. DuckDB の `metadata_records` テーブルに対し、`decisions.parquet` から一括UPDATEを実行：
     ```sql
     UPDATE metadata_records AS m
     SET
         type_status = s.type_status,
         type_reason = s.type_reason,
         about_status = s.about_status,
         about_reason = s.about_reason,
         ngram_status = s.ngram_status,
         ngram_reason = s.ngram_reason,
         llm_status = s.llm_status,
         llm_reason = s.llm_reason,
         final_decision = s.final_decision,
         human_decision = s.human_decision,
         primary_reason = s.primary_reason,
         adopted_stage = s.adopted_stage,
         drop_stage = s.drop_stage
     FROM read_parquet(?) AS s
     WHERE m.id = s.id;
     ```
  DuckDBのインメモリカラムナ処理により、数十万件でも数百ミリ秒で瞬時に以前の作業状態へ行き来できます。

### 2.3 データ共有・他者引継ぎパッケージ (Layer 3)
2種類のエクスポート/インポートを提供します：

1. **軽量レシピパッケージ（Rule & Manifest Bundle: `.zip` / 10MB以下）**:
   * **内容**: `acquisition_manifest.json`, `rules/`, `human_verified_cleaned.jsonl`, `prisma_flow_summary.json`
   * **用途**: 共同研究者への判定ルール共有、論文付録（Supplementary Data）。他者はこのレシピをインポートし、マニフェストに基づいて同一のデータを再現可能。
2. **完全アーカイブパッケージ（Full Dataset Archive: `.tar.gz` / 大容量）**:
   * **内容**: 生データ（JSONL）、DuckDB、ルール一式、全監査トレイルCSV、エクスポート成果物。
   * **用途**: オフライン環境への完全移行、長期データ保存（Zenodo/機関リポジトリ登録用）。

---

## 3. 既存コードへの統合と変更ファイル一覧

現状のコードベースでは、各ビュー（`views/step*.py`）は `paths: dict` を引数に取ってファイルを参照しています。そのため、**各ビューの内部コードを壊すことなく、`app.py` から渡す `paths` 辞書を動的生成する形**で統合可能です。

| ファイル | 役割と変更内容 |
| :--- | :--- |
| `01_cleansing_studio/modules/workspace_manager.py` (新規) | ワークスペースのCRUD、パス解決、スナップショット保存・復元、ZIPエクスポート/インポートを担当するコアエンジン |
| `01_cleansing_studio/views/workspace_view.py` (新規) | ワークスペース切替・作成、スナップショットタイムライン、インポート/エクスポートを行う管理画面 |
| `01_cleansing_studio/app.py` | サイドバー最上部に「ワークスペース切替」セレクタの追加、アクティブワークスペースのパス動的注入、管理画面ルーティングの追加 |
| `01_cleansing_studio/run_fetch_worker.py` | コマンドライン引数 `--workspace-dir` / `--workspace-id` の追加（特定ワークスペースへのバックグラウンド取得） |
| `01_cleansing_studio/test_pipeline.py` | ワークスペース分離、スナップショット保存・復元、インポート・エクスポートの単体/統合テスト追加 |

---

## 4. 後方互換性と移行計画

既存の「雅楽」データ（`data/raw_metadata.jsonl`, `metadata_store.duckdb`, `complete_audit_trail.csv` 等）を安全に保護するため、以下の移行ロジックを実装します：

1. **初回起動時の自動検知**:
   * `data/workspaces/` が存在しない、または空の場合に起動すると、ルート直下の `data/` および `rules/` の既存ファイルを検知。
   * `data/workspaces/gagaku_default/` を自動作成し、既存のデータセットを安全にワークスペース構造へ組み込み（またはシンボリックリンク/移動）。
   * ルート直下にも互換性のための参照を維持するか、透過的に `gagaku_default` を参照することで、既存のスクリプトやビューアが一切壊れない設計にします。

---

## 5. UI/UX 設計

1. **サイドバー（常設UI）**:
   * 最上部にアイコン付きのワークスペースセレクタ：
     `📁 [雅楽コレクション (デフォルト) ▼]`
   * 横に「＋新規作成」「⚙️ 管理」ボタンを配置。
2. **プロジェクト＆履歴マネージャー（管理画面）**:
   * **タブ 1: ワークスペース一覧・管理**:
     * プロジェクト名、説明、作成日、データ件数、ディスク使用量のカード表示。
     * 「新規作成（空から作成 / 既存ルールを引き継いで作成）」「複製」「削除」。
   * **タブ 2: フィルタリング作業履歴（スナップショット）**:
     * 「現在の状態でスナップショットを保存」ボタン（メモ入力欄付き）。
     * 履歴タイムライン（保存日時、合格数/除外数、メモ）。
     * 「この状態に復元する」ボタン（ワンクリックでルールとDuckDBステータスがロールバック）。
   * **タブ 3: データ共有・他者引継ぎ**:
     * エクスポート: 「軽量レシピ (.zip)」または「完全アーカイブ」のダウンロード。
     * インポート: ドラッグ＆ドロップでZIPをアップロードし、新しいワークスペースとして即座に展開・再開。

---

## 6. 検証・受け入れ基準
1. **後方互換性**: 既存の「雅楽」メタデータとルールが何の手間もなくそのまま読み込め、ダッシュボードや各工程の表示が正常であること。
2. **ワークスペース分離**: 新規ワークスペース（例: `test_project`）を作成・切り替えた際、既存の雅楽データと混ざらず、独立してStep 1〜Step 5を実行できること。
3. **スナップショット復元**: ルールを変更した後にスナップショットを復元すると、ルールファイルおよびDuckDBの判定ステータスカラムが瞬時に過去の状態へ戻ること。
4. **パッケージの引き継ぎ**: エクスポートしたZIPをインポートして新規ワークスペースを作成し、同一の状態で作業を再開できること。
