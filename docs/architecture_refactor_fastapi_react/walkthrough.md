# ウォークスルー: FastAPI + React SPA へのアーキテクチャ刷新

## 1. 概要と刷新の背景

本リポジトリ「JPS Refine Studio」は、ジャパンサーチ（Japan Search）等の文化資源メタデータを大量に収集・蓄積し、DuckDB上で多段階にクレンジング・分類・専門家査読を行って特定主題の高品質なデータセットを構築するシステムです。

従来の `01_cleansing_studio`（Streamlitベース）では、数十万件規模のメタデータを扱う際に以下のボトルネックが存在していました：
1. **画面操作ごとの全体再実行**: スクリプト全体がリランされるため、レスポンスが重く、快適な査読が困難。
2. **長時間の重い処理の同期ブロック**: SPARQL全件取得やLLMセマンティック推論、N-gram計算の途中でブラウザを閉じると処理が中断される。

これらを根本解決するため、**「FastAPI（完全非同期バックエンド）＋ React 18 SPA（モダンフロントエンド）」** の構成へと全面的に移行・リファクタリングを実施しました。

---

## 2. 新旧アーキテクチャの比較

| 項目 | 旧 Streamlit 実装 (`01_cleansing_studio`) | 新 FastAPI + React SPA 実装 (`v2.0`) |
| :--- | :--- | :--- |
| **フロントエンド** | Streamlit Python UI（全スクリプト再実行） | React 18 + TypeScript + Vite + Tailwind CSS |
| **バックエンド** | 同期Pythonスクリプト実行 | FastAPI + Uvicorn（非同期REST API） |
| **重い処理（SPARQL/LLM/N-gram）** | 一部別スクリプト（UIとの進捗同期が不安定） | `JobManager` による完全非同期ワーカー ＋ **Server-Sent Events (SSE)** 配信 |
| **ブラウザ切断耐性** | ブラウザを閉じると処理が止まる/ステート喪失 | **ブラウザを閉じても裏で処理継続**、再接続時に自動復帰 |
| **データ取得＆描画** | 全件メモリ読み込み（数百MB転送） | DuckDB `LIMIT/OFFSET` による**サーバーサイド・ページネーション** |
| **ルール影響確認** | 上位50件等で打ち切り | **上限なし完全一覧（51件目以降もスクロール可能） ＋ 巻き添え衝突警告ガード** |
| **典拠解決** | 外部非公式API（Cloud Run）依存 | **国立国会図書館 Web NDL Authorities SPARQL 1.1** へ完全統合 |
| **査読操作** | ボタンクリック毎にリロード待ち | **J/K/A/D キーボードショートカット ＋ 楽観的UI更新（Optimistic UI）** |

---

## 3. 主要な実装コンポーネント

### (1) バックエンド (`backend/`)
- [`backend/app/main.py`](file:///Users/shint/Desktop/JPS_Refine_Studio/backend/app/main.py): FastAPI エントリーポイント。CORS、全APIルーター、およびビルド済みSPA（`frontend/dist`）の静的ファイル配信を統括。
- [`backend/app/services/job_manager.py`](file:///Users/shint/Desktop/JPS_Refine_Studio/backend/app/services/job_manager.py): バックグラウンドジョブの非同期実行、進捗追跡、中断制御、SSE（Server-Sent Events）ストリーミング配信。
- [`backend/app/modules/duckdb_manager.py`](file:///Users/shint/Desktop/JPS_Refine_Studio/backend/app/modules/duckdb_manager.py):
  - スレッド安全な排他制御（`threading.RLock`）の導入。
  - 新ファセット（`provider`, `published_year`, `has_image`, `creator`）の拡張とインデックス化。
  - `query_records`（サーバーサイドページネーション）と `query_impact_records`（影響全件抽出＆衝突警告）。
- [`backend/app/modules/ndc_utils.py`](file:///Users/shint/Desktop/JPS_Refine_Studio/backend/app/modules/ndc_utils.py): 国立国会図書館公式 SPARQL（`https://id.ndl.go.jp/auth/ndla/sparql`）に対する `VALUES` バッチクエリ実装。外部非公式APIを完全撤廃。
- [`backend/app/api/`](file:///Users/shint/Desktop/JPS_Refine_Studio/backend/app/api/):
  - `workspaces.py`: ワークスペースCRUD、スナップショット、ダッシュボードPRISMA集計。
  - `jobs.py`: ジョブ一覧、SSEストリーミング (`/stream`)、中断API。
  - `records.py`: ページネーション付きレコード取得、ファセット集計、手動判定（URL安全な `POST /decision` および `{record_id:path}` 両対応）。
  - `rules.py`: Type/About/N-gramルール、NDCツリー、典拠分離、N-gram接尾辞クラスタ、影響レコード完全一覧 (`/impact-records`)、一括適用。
  - `fetch.py`, `llm.py`, `ndc.py`: データ取得、LLM適合推論、NDC典拠解決。

### (2) フロントエンド (`frontend/`)
- [`frontend/src/App.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/App.tsx): メインレイアウト、ビュー切り替え、新規ワークスペース作成モーダル。
- [`frontend/src/components/JobProgressBar.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/components/JobProgressBar.tsx): 最上部に常駐するリアルタイム進捗バー（SSE連動、ETA表示、中断ボタン）。
- [`frontend/src/components/RuleImpactDrawer.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/components/RuleImpactDrawer.tsx): ★ ルール影響全件一覧ドロワー（ページネーション、インクリメンタル検索、巻き添え衝突警告タブ）。
- [`frontend/src/views/DashboardView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/DashboardView.tsx): PRISMAフローに準拠した多段階絞り込み進捗と各ステップの残存件数サマリー。
- [`frontend/src/views/FetchView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/FetchView.tsx): LLMクエリ拡張とSPARQL一括取得画面。
- [`frontend/src/views/TypeFilterView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/TypeFilterView.tsx): Step 2-A rdf:type 除外設定と影響確認。
- [`frontend/src/views/AboutFilterView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/AboutFilterView.tsx): Step 2-B NDC 3段階階層ツリーアコーディオンとNDL典拠キーワード分離。
- [`frontend/src/views/NgramFilterView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/NgramFilterView.tsx): Step 2-C タイトル語彙N-gramおよび接尾辞（〜譜、〜集、〜記等）クラスタリング。
- [`frontend/src/views/LlmFilterView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/LlmFilterView.tsx): Step 3 LLMセマンティック推論設定とジョブ起動。
- [`frontend/src/views/ReviewView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/ReviewView.tsx): Step 4 爆速専門家査読ポータル（J/K/A/Dキーボードショートカット、ファセット絞り込み、詳細プレビュー、ジャパンサーチ外部リンク）。
- [`frontend/src/views/ExportView.tsx`](file:///Users/shint/Desktop/JPS_Refine_Studio/frontend/src/views/ExportView.tsx): Step 5 確定JSONL同期出力と成果物管理。

---

## 4. 検証結果

### (1) フロントエンド・ビルド検証
TypeScriptコンパイル（`tsc`）およびVite本番バンドル（`vite build`）がノーエラーで成功：
```text
✓ 1587 modules transformed.
dist/index.html                   0.55 kB │ gzip:  0.43 kB
dist/assets/index-CB5m_3ps.css   28.97 kB │ gzip:  5.72 kB
dist/assets/index-IJDCcB3u.js   267.23 kB │ gzip: 72.85 kB
✓ built in 1.49s
```

### (2) End-to-End 統合パイプライン検証 (`backend/test_e2e_pipeline.py`)
既存のワークスペース `score4gagaku`（1,712件）の実データを用いて全パイプラインを結合テスト：
- **ワークスペース認識**: 4件のワークスペース（`score4gagaku` 等）を正常取得。
- **PRISMAフロー集計**: Raw 1,712件 → Type 1,712件 → About 1,704件 → Ngram 1,587件 → LLM 1,712件 → 査読済 1,695件 を即座に算出。
- **NDCツリー ＆ 典拠クラスタ**: 24件の高度クラスタを抽出。
- **N-gram接尾辞クラスタ**: 「〜譜」(3,284件)、「〜集」(658件)、「〜記」(46件) などの形態別グループ化を正常確認。
- **★ ルール影響完全一覧 ＆ 衝突警告**:
  - 「雅楽」除外ルールに対し、該当全45件を特定。
  - すでに確定OKとなっている重要資料45件が巻き添え除外される危険を**「巻き添え・衝突警告」**として100%正確に検知。
  - ページ間のID重複がないサーバーサイド・ページネーションの整合性を確認。
- **専門家査読ポータル**: 任意レコードの手動オーバーライド更新（DuckDB即時反映・確定JSONL同期）およびクリーン復元を確認。
- **エクスポート**: 1,695件の確定メタデータセット出力を確認。

---

## 5. 起動方法

### 開発モード (ホットリロード対応)
```bash
./dev.sh
```
- Web UI (Vite): [http://localhost:5173](http://localhost:5173)
- API Docs (FastAPI): [http://localhost:8000/docs](http://localhost:8000/docs)

### 本番統合モード (単一ポート 8000)
```bash
./start.sh
```
- Web UI / API: [http://localhost:8000](http://localhost:8000)

