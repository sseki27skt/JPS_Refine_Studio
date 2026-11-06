# JPS-Refine Studio アーキテクチャ刷新・統合実装計画書
（FastAPI + React SPA + Web NDL Authorities + 高度クラスタリング）

## 1. 刷新の背景と目的
本システム「JPS Refine Studio」は、ジャパンサーチ等の外部SPARQLエンドポイントから大量の文化資源・学術メタデータを取得し、DuckDB上で多段階フィルタリング、LLMセマンティック推論、および専門家による査読を経て高純度なメタデータサブセットを構築するツールです。

現行の Streamlit アプリケーション（`01_cleansing_studio`）が抱える以下の根本課題を解決するため、**FastAPI（非同期バックエンド）＋ React SPA（モダンフロントエンド）** へ全面的に移行します：
1. **大量データ描画の重延化**: UI操作のたびにPython全体が再実行されるオーバーヘッドを廃止し、ミリ秒単位のサーバーサイドページネーション（DuckDB `LIMIT/OFFSET`）と仮想スクロール（TanStack Virtual）で数十万件のメタデータを軽快に描画。
2. **重い処理の完全非同期化**: SPARQL取得、LLM判定、N-gram構築などの数時間タスクを `JobManager` によりブラウザから完全に切り離し、SSE（Server-Sent Events）でリアルタイム進捗配信。ブラウザを閉じても裏で安全に継続。
3. **フィルタリング影響の「完全全件検証」とセーフティガード**: 50件等の上限で打ち切らず、影響を受ける全レコード（何万件でも）を仮想スクロールで一覧・検索可能にし、確定OKの巻き添え除外を即座に検知する衝突警告タブを新設。
4. **公的典拠統合（Web NDL Authorities）**: 外部非公式APIを全廃し、国立国会図書館の公式SPARQLエンドポイントによりNDC/NDLC/NDLNAを一括解決。
5. **高度な候補クラスタリング**: NDCの3段階階層ツリー化、NDL典拠の種別分離、タイトルN-gramの接尾辞（「〜譜」「〜集」）クラスタリングにより、ルール設定作業を直感化・効率化。

---

## 2. システム全体アーキテクチャ

```mermaid
flowchart TD
    subgraph Frontend ["Frontend (React SPA / Vite + TypeScript + Tailwind CSS)"]
        VIEWS["UI Views<br>(Workspace / Fetch / Type / About / Ngram / Review / Dashboard)"]
        DRAWER["★ RuleImpactDrawer<br>(ルール影響全件一覧 & 衝突警告タブ)"]
        TABLE["TanStack Table & Virtual<br>(仮想スクロール & サーバーサイドページネーション)"]
        HOOKS["Hooks (useWorkspace, useJobStatus, useRecords)"]
        SSE_CLIENT["SSE Client (EventSource)"]
        API_CLIENT["API Client (Axios / Fetch)"]

        VIEWS --> DRAWER
        VIEWS --> TABLE
        VIEWS --> HOOKS
        HOOKS --> SSE_CLIENT
        HOOKS --> API_CLIENT
    end

    subgraph Backend ["Backend (FastAPI Server + Background Worker)"]
        ROUTERS["API Routers<br>(workspaces, jobs, records, rules, fetch, llm, ndc)"]
        JOB_MGR["★ JobManager<br>(asyncio / ThreadPool, 状態・進捗永続化, SSEキュー)"]
        SERVICES["Services<br>(WorkspaceService, RecordService, RuleService, NdcService)"]
        SSE_ENDPOINT["/api/jobs/{id}/stream (SSE)"]

        ROUTERS --> SERVICES
        ROUTERS --> JOB_MGR
        JOB_MGR --> SSE_ENDPOINT
    end

    subgraph CoreEngine ["既存エンジン & 外部連携"]
        DUCK["DuckDBManager (Single-Process Connection Pool)<br>metadata_store.duckdb"]
        RULES["rule_filter.py / ngram_index.py / about_index.py"]
        SPARQL["sparql_collector.py (3階層CONSTRUCT再帰取得)"]
        LLM["llm_classifier.py (Web補強セマンティック判定)"]
        WS_MGR["workspace_manager.py (スナップショット/エクスポート)"]
        NDL_SPARQL["Web NDL Authorities SPARQL 1.1<br>(https://id.ndl.go.jp/auth/ndla/sparql)"]

        SERVICES --> DUCK
        SERVICES --> RULES
        SERVICES --> WS_MGR
        SERVICES --> NDL_SPARQL
        JOB_MGR --> SPARQL
        JOB_MGR --> LLM
        JOB_MGR --> DUCK
    end

    Frontend <-->|REST API (JSON)| Backend
    SSE_ENDPOINT -->|SSE Event Stream| SSE_CLIENT
```

---

## 3. 主要機能と設計仕様

### 3.1 完全非同期バックグラウンドジョブ制御（JobManager + SSE）
- **対象タスク**:
  - SPARQLクエリ実行および3階層CONSTRUCTトリプル再帰取得（Step 1）
  - ルール一括適用およびDuckDBステータス更新（Step 2-A/B/C）
  - 判定保留群に対する外部Web検索＋LLMセマンティック推論（Step 3）
  - タイトルN-gramインデックス構築および主題転置インデックス構築
- **ジョブ状態管理**:
  - 状態: `PENDING`, `RUNNING`, `COMPLETED`, `STOPPED`, `FAILED`
  - メトリクス: `current`, `total`, `percentage`, `eta_seconds`, `stage`, `error_message`
  - ワークスペースごとの `fetch_job_status.json` に即時フラッシュし、ブラウザリロードやサーバー再起動時にも最新状態を復元。
- **SSE配信**: `/api/jobs/{job_id}/stream` により1秒間隔（または更新時）に進捗イベントをストリーミング配信。

### 3.2 フィルタリング影響レコードの「完全一覧化」＆衝突警告
- **エンドポイント**: `POST /api/workspaces/{id}/rules/impact-records`
- **設計仕様**:
  - 上限（50件等）で打ち切らず、該当する全レコード（1,000件でも50,000件でも）を DuckDB の `LIMIT ? OFFSET ?` でページング返却。
  - フロントエンド側は `RuleImpactDrawer.tsx`（TanStack Virtual）で軽快に全件スクロール・閲覧可能。
  - **衝突警告タブ（セーフティガード）**:
    - すでに「合格確定（手動OK・ルールOK）」または「LLM適合（is_target: true）」になっているレコードが影響対象に含まれる場合、赤色バッジで警告し、そのレコードのみをワンクリックで抽出して例外保護・確認可能。
  - **インクリメンタル検索**:
    - 影響レコード群の内部でタイトルや説明文の部分一致検索・ソートが可能。

### 3.3 メタデータ属性の拡張（新規ファセット検索）
- **DuckDBスキーマ拡張**:
  ```sql
  ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS provider VARCHAR;        -- 所蔵館・提供DB
  ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS published_year INTEGER;  -- 出版年・制作年
  ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS has_image BOOLEAN;       -- 画像/IIIF有無
  ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS creator VARCHAR;         -- 著者・編者
  ```
- **インデックス作成**: `provider`, `published_year`, `has_image` に対するインデックスを作成し、`records/facets` API で所蔵館別・年代別の件数分布をミリ秒で返却。

### 3.4 Web NDL Authorities SPARQL による NDC/NDLC/NDLNA 統合
- **外部非公式API（`api-4pccg7v5ma-an.a.run.app`）を完全撤廃**。
- `https://id.ndl.go.jp/auth/ndla/sparql` を用いて、NDC分類記号に `skos:relatedMatch` で紐づく公式普通件名ラベルを一括バッチ解決。
- `ndc_api_cache.json` にローカル永続化し、2回目以降はゼロ秒で解決。

### 3.5 候補クラスタリングの刷新
1. **NDCの3段階階層ツリークラスタリング**:
   - `類（1桁: 7 芸術）` ＞ `綱（2桁: 76 音楽）` ＞ `目（3桁: 768 邦楽）`
   - UI上でアコーディオン展開し、無関係な大綱（4自然科学、5工学など）を一括除外可能に。
2. **NDL典拠の種別分離**:
   - `普通件名（NDLSH）`: ジャンル・概念・形態
   - `人名典拠（NDLNA）`: 作曲家・作詞者・演奏家・名跡
   - `団体名典拠（NDLNA）`: 機関・劇団・文庫
3. **タイトルN-gramの接尾辞（Suffix）クラスタリング**:
   - 「〜譜」「〜集」「〜図」「〜録」「〜論」「〜記」などの共通形態素末尾で自動グループ化。
   - 「〜譜」グループ内で「画譜（NG）」「棋譜（NG）」と「箏譜（OK）」を横並びで即座に選別可能。

### 3.6 専門家査読ポータル（Step 4 / 2d）の高速化
- **キーボードナビゲーション**:
  - `J` / `K`: レコード間を上下移動
  - `A`: 合格（Accept）
  - `D`: 除外（Discard）
  - `G`: 保留（Grey）
- **楽観的UI更新（Optimistic Update）**:
  - キーストロークの瞬間にフロント側のバッジが切り替わり、裏で非同期に `PATCH /records/{id}/decision` を送信。待機時間ゼロで流れるように判定可能。
- **原典リンク＆差分ハイライト**:
  - ジャパンサーチ・NDLデジタルコレクションへの外部リンク。
  - 除外理由となったN-gramパターンやAbout分類を色付きタグで強調表示。

---

## 4. ディレクトリ構成

```text
JPS_Refine_Studio/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPIエントリーポイント・CORS設定
│   │   ├── config.py                   # パス解決・環境変数設定
│   │   ├── schemas/                    # Pydantic スキーマ定義
│   │   │   ├── workspace.py
│   │   │   ├── job.py
│   │   │   ├── record.py
│   │   │   ├── rule.py
│   │   │   └── fetch.py
│   │   ├── api/                        # APIルーター群
│   │   │   ├── workspaces.py           # ワークスペース・スナップショット管理
│   │   │   ├── jobs.py                 # ジョブ制御・SSEストリーム
│   │   │   ├── records.py              # レコード取得（ファセット対応）・査読更新
│   │   │   ├── rules.py                # ルール管理・影響全件一覧・適用
│   │   │   ├── fetch.py                # SPARQLクエリ拡張・取得開始
│   │   │   └── llm.py                  # LLM適合判定ジョブ起動
│   │   ├── services/                   # ビジネスロジック連携・ワーカー制御
│   │   │   ├── job_manager.py          # ジョブ管理とSSEキュー制御
│   │   │   ├── workspace_service.py
│   │   │   ├── record_service.py
│   │   │   ├── rule_service.py
│   │   │   └── ndc_service.py          # Web NDL Authorities SPARQL統合解決
│   │   └── modules/                    # 01_cleansing_studio/modulesから移植・再利用
│   │       ├── duckdb_manager.py
│   │       ├── workspace_manager.py
│   │       ├── sparql_collector.py
│   │       ├── rule_filter.py
│   │       ├── ngram_filter.py
│   │       ├── ngram_index.py
│   │       ├── about_index.py
│   │       ├── llm_classifier.py
│   │       ├── llm_query_expander.py
│   │       ├── ndc_utils.py
│   │       └── logger.py
│   ├── requirements.txt
│   └── run.py                          # サーバー起動スクリプト
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts                  # /api へのリバースプロキシ (localhost:8000)
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── api/                        # APIクライアント & SSE
│   │   │   ├── client.ts
│   │   │   └── sse.ts
│   │   ├── components/                 # 共通UI
│   │   │   ├── Header.tsx              # 上部バー、ワークスペース切替
│   │   │   ├── Sidebar.tsx             # ステップ遷移ナビゲーション
│   │   │   ├── JobProgressBar.tsx      # 常駐ジョブ進捗バー
│   │   │   ├── DataTable.tsx           # 高速ページングテーブル（TanStack Table）
│   │   │   └── RuleImpactDrawer.tsx    # ★ ルール影響全件一覧（衝突警告タブ付き）
│   │   ├── views/                      # 各画面
│   │   │   ├── WorkspaceView.tsx       # プロジェクト・履歴マネージャー
│   │   │   ├── DashboardView.tsx       # PRISMAフロー全体進捗
│   │   │   ├── FetchView.tsx           # Step 1: SPARQLメタデータ取得
│   │   │   ├── TypeFilterView.tsx      # Step 2-A: rdf:type 除外
│   │   │   ├── AboutFilterView.tsx     # Step 2-B: schema:about (NDC階層ツリー & 典拠分離)
│   │   │   ├── NgramFilterView.tsx     # Step 2-C: タイトルN-gram (接尾辞クラスタリング)
│   │   │   ├── LlmFilterView.tsx       # Step 3: LLM適合判定
│   │   │   ├── ReviewView.tsx          # Step 4: 専門家査読ポータル (J/K/A/Dキーボード操作)
│   │   │   └── ExportView.tsx          # Step 5: エクスポート
│   │   ├── hooks/
│   │   │   ├── useWorkspace.ts
│   │   │   ├── useJobStatus.ts
│   │   │   └── useRecords.ts
│   │   ├── types/
│   │   │   └── api.ts
│   │   ├── App.tsx
│   │   └── index.css
│
└── 01_cleansing_studio/                # 現行資産（比較検証用として温存）
```

---

## 5. 事前に検討・確認しておくべき論点・リスク（事前検討事項）

実装着手前にあらかじめ方針を明確にしておくべき技術的論点は以下の4点です：

### 論点①: DuckDBの排他的ロックと単一プロセス接続管理
- **課題**:
  DuckDBは組み込み型列指向データベースであり、同一ファイルに対して複数プロセスから書き込みアクセスを行うと `duckdb.IOException: Could not set lock on file` が発生します。
- **対策**:
  - バックグラウンドジョブ（SPARQL取得、LLM推論、ルール適用）は別プロセス（`subprocess`）ではなく、FastAPIサーバー内の `asyncio` / `ThreadPoolExecutor` ワーカーとして同一プロセス内で実行します。
  - FastAPIサーバー内にスレッド安全な `DuckDBManager` シングルトン／コネクション管理を設け、APIリクエストによるクエリとバックグラウンドタスクによるバッチ更新がロック衝突を起こさないように制御します。

### 論点②: 既存DBファイルに対する自動スキーママイグレーション
- **課題**:
  `score4gagaku` 等の既存DuckDBファイルには、新設する `provider`, `published_year`, `has_image`, `creator` のカラムが存在しません。
- **対策**:
  - `DuckDBManager._init_schema()` 実行時に `ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS ...` を自動実行します。
  - 既存データに対しては、`raw_json` からこれらの属性を抽出して補完（Backfill）する軽量スクリプトを初回ロード時に走らせる設計にします。

### 論点③: Web NDL Authorities SPARQL のレートリミット対策
- **課題**:
  国立国会図書館の SPARQL エンドポイントに過大な連続リクエストを送ると、503エラーやタイムアウトが発生するリスクがあります。
- **対策**:
  - `VALUES` 句を用いて最大100件ずつ一括バッチ問い合わせ（Bulk Fetch）を行います。
  - 一度解決した結果は `ndc_api_cache.json` に即時永続化し、再問い合わせを完全に防止します。

### 論点④: 配布・起動の利便性（開発モードとスタンドアロン起動）
- **方針**:
  - 開発時: `backend`（Uvicorn: 8000）と `frontend`（Vite: 5173）を別々に起動。
  - 本番/単体配布時: フロントエンドをビルド（`npm run build`）し、FastAPI側から静的ファイルとして配信することで、`python run.py` 一発でブラウザが立ち上がる構成をサポートします。
