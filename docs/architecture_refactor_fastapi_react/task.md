# タスク進捗管理: FastAPI + React アーキテクチャ刷新

- [x] **Phase 1: リポジトリの現状分析と移行計画の策定** <!-- id: phase1 -->
  - [x] 既存コードベース調査（`01_cleansing_studio` のモジュール、ビュー、DuckDBスキーマ、既存バックグラウンド処理） <!-- id: phase1-1 -->
  - [x] ユーザビリティ改善検討（ルール影響レコードの完全一覧化、新規ファセット属性、NDCのWeb NDL Authorities統合、高度クラスタリング） <!-- id: phase1-2 -->
  - [x] 事前検討論点（DuckDBロック制御、マイグレーション、SPARQLレート制御、起動構成）の整理 <!-- id: phase1-3 -->
  - [x] FastAPIエンドポイント定義およびPydanticスキーマ設計 <!-- id: phase1-4 -->
  - [x] 詳細実装計画書（`implementation_plan.md`）の作成 <!-- id: phase1-5 -->

- [x] **Phase 2: FastAPIバックエンド基盤の実装** <!-- id: phase2 -->
  - [x] `backend/` ディレクトリ構成のセットアップと依存パッケージ導入（`uv add fastapi uvicorn sse-starlette pydantic requests` 等） <!-- id: phase2-1 -->
  - [x] Web NDL Authorities SPARQL統合（`ndc_utils.py` の刷新：NDC/NDLC/NDLNA一括バッチ解決） <!-- id: phase2-2 -->
  - [x] DuckDBスキーマ拡張（`provider`, `published_year`, `has_image` カラム・インデックス化）とコネクション制御 <!-- id: phase2-3 -->
  - [x] ワークスペース管理API（`api/workspaces.py`）の実装 <!-- id: phase2-4 -->
  - [x] ジョブ管理マネージャー（JobManager）とSSEストリーミングAPI（`api/jobs.py`）の実装 <!-- id: phase2-5 -->
  - [x] レコード取得（ファセット検索対応）・査読更新API（`api/records.py`）の実装 <!-- id: phase2-6 -->
  - [x] フィルタ・クレンジングルール管理および影響レコード完全一覧API（`api/rules.py`）の実装 <!-- id: phase2-7 -->
  - [x] SPARQL取得・LLM推論サービス連携API（`api/fetch.py`, `api/llm.py`）の実装 <!-- id: phase2-8 -->
  - [x] バックエンドAPIの単体テスト・疎通確認 <!-- id: phase2-9 -->

- [x] **Phase 3: Vite + Reactフロントエンド基盤の構築** <!-- id: phase3 -->
  - [x] `frontend/` プロジェクト初期化（Vite + React + TypeScript + Tailwind CSS） <!-- id: phase3-1 -->
  - [x] APIクライアント（Fetch/Axios）およびSSEジョブ監視フック（`useJobStatus`）の実装 <!-- id: phase3-2 -->
  - [x] 共通レイアウト（ヘッダー、サイドバー、ジョブ進行バー、ナビゲーション）の実装 <!-- id: phase3-3 -->
  - [x] ワークスペース管理ビュー（`WorkspaceView.tsx`）の実装 <!-- id: phase3-4 -->
  - [x] ダッシュボードビュー（`DashboardView.tsx`）の実装 <!-- id: phase3-5 -->
  - [x] Step 1: SPARQLメタデータ取得ビュー（`FetchView.tsx`）の実装 <!-- id: phase3-6 -->
  - [x] Step 2-A: rdf:type 除外ビュー（`TypeFilterView.tsx`）の実装 <!-- id: phase3-7 -->
  - [x] Step 2-B: schema:about キーワード分類ビュー（`AboutFilterView.tsx`、NDC階層ツリー＆典拠分離）の実装 <!-- id: phase3-8 -->
  - [x] Step 2-C: タイトルN-gram除外ビュー（`NgramFilterView.tsx`、接尾辞クラスタリング）の実装 <!-- id: phase3-9 -->
  - [x] ★ ルール影響レコード完全一覧ドロワー（`RuleImpactDrawer.tsx`、衝突警告タブ付き）の実装 <!-- id: phase3-10 -->
  - [x] Step 3: LLM適合判定ビュー（`LlmFilterView.tsx`）の実装 <!-- id: phase3-11 -->
  - [x] Step 4: 専門家査読ポータル（`ReviewView.tsx`、TanStack Table/Virtual、J/K/A/Dキーボード操作）の実装 <!-- id: phase3-12 -->
  - [x] Step 5: エクスポートビュー（`ExportView.tsx`）の実装 <!-- id: phase3-13 -->

- [x] **Phase 4: 統合動作検証とクリーンアップ** <!-- id: phase4 -->
  - [x] 既存DuckDBデータ（`score4gagaku`等）を用いたEnd-to-End動作検証 <!-- id: phase4-1 -->
  - [x] ルール影響レコードの完全一覧（51件目以降のスクロール・検索・衝突警告）の動作検証 <!-- id: phase4-2 -->
  - [x] バックグラウンドジョブの実行・ブラウザリロード・SSE再接続の耐障害性検証 <!-- id: phase4-3 -->
  - [x] 起動スクリプト・README（Backend/Frontendの起動手順）の整備 <!-- id: phase4-4 -->
  - [x] `walkthrough.md` の作成と完了報告 <!-- id: phase4-5 -->
