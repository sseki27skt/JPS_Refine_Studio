# JPS-Refine Studio (ジャパンサーチ・メタデータ精緻化＆検索スタジオ)

文化資源メタデータ（ジャパンサーチ / Japan Search 等）からノイズを高精度に除外・精緻化し、学術研究やデジタルアーカイブとして活用するための統合研究・開発プラットフォームです。

「譜」という文字の多義性（家譜、年譜、画譜などの非音楽資料）を多段階で系統的に排除し、真正な楽譜資料を効率的に抽出・構造化するために開発されました。

---

## 🌟 主な特徴とアーキテクチャ

### 1. 多段階ハイブリッド・クレンジングパイプライン (`01_cleansing_studio`)
- **Step 1: データ収集 ＆ バックグラウンド非同期ワーカー**:
  - LLMを活用した検索語彙拡張とSPARQLクエリ自動生成による網羅的収集。
  - バックグラウンドワーカー（`run_fetch_worker.py`）による非同期実行。画面を閉じても処理が継続し、いつでも進捗保存＆中断再開（レジューム）が可能。
- **Step 2-A: データ種別 (`rdf:type`) フィルタ**:
  - 記事・論文、公演、絵画、絵葉書などの不要なリソース型を大分類ノイズとして高速除外。
- **Step 2-B: 主題 (`schema:about`) フィルタ**:
  - 日本十進分類法（NDC 9版/10版）および国立国会図書館典拠データ（Web NDL Authorities）と連動した高速主題判定。
- **Step 2-C: タイトル語彙・N-gram フィルタ**:
  - タイトルに含まれる頻出語彙（N=2〜9のN-gram部分文字列）や接尾辞・任意パターンの分析・除外。
- **Step 3: LLMセマンティック適合判定**:
  - 事前ルールで合否を断定できなかった「判定保留（グレーゾーン）」群のみを DuckDB 高速エンジンで自動抽出し、ローカル/クラウドLLMにより文脈・解題記述をセマンティック推論。
- **Step 4: 専門家査読ポータル**:
  - DuckDB サーバーサイドページネーションにより、数万件規模のメタデータでも軽快に検索・閲覧し、専門家による手動オーバーライドと確定判定を即座に記録。
- **Step 5: 統合データ出力 ＆ 学術監査パッケージ**:
  - 公開用ビューアデータ（`scores_data.json`）、完全監査証跡CSV（`complete_audit_trail.csv`）、およびPRISMA 2020 準拠フローレポート（Markdown / JSON）を一括生成。

### 2. DuckDB 高速メタデータ管理エンジン
- 数万〜十数万件規模の文化資源メタデータに対し、カラムナ型データベース DuckDB を統合。
- ルール判定、正規表現マッチ、N-gram集計、ステータス更新をミリ秒〜数秒で実行し、メモリ消費を大幅に抑制。

### 3. 学術的再現性 ＆ 追跡可能性 (Provenance & Audit Trail)
- **取得条件マニフェスト (`acquisition_manifest.json`)**:
  - SPARQLクエリ全文、検索キーワード、包含・除外NDC、正規表現パターン、収集日時を自動記録。
- **完全監査証跡 (`complete_audit_trail.csv`)**:
  - 母集団全件に対し、どの段階（Type / Rule / LLM / Human）で、どのような根拠・理由で採否が決定されたかを網羅。
- **PRISMA 2020 準拠フローレポート**:
  - 初期同定から各段階での脱落内訳、最終採択までの系統的絞り込みフロー図（Mermaid）と除外理由ランキングを自動算出。

### 4. 研究テーマ別ワークスペース ＆ スナップショット管理
- **ワークスペース分離**:
  - 雅楽、浮世絵、能楽、古地図など、テーマごとに独立した作業空間（データ・ルール・スナップショット）を管理。
- **超高速スナップショット（試行錯誤の行き来）**:
  - ルール定義とDuckDB判定ステータスのみを軽量Parquet（約1MB）で瞬時にバックアップし、ワンクリックで以前の試行錯誤状態へ復元。
- **データ共有・引き継ぎパッケージ**:
  - 共同研究者への配布用「軽量レシピパッケージ（.zip）」および「完全アーカイブ（.zip）」のエクスポート/インポートに対応。

### 5. 高速＆インタラクティブな検索ビューア (`02_search_viewer`)
- 精緻化されたメタデータを即座にブラウジング可能な静的Webアプリケーション（サーバーレスでGitHub Pages等に公開可能）。
- ジャンル、演奏楽器、提供機関による多角的ファセット絞り込みと Chart.js による統計可視化。
- **「資料カタログ検索」と「PRISMA 絞り込みプロセス ＆ 再現性」の一体提示**: 各資料カードでの採択根拠バッジ表示、初期抽出条件・フロー図の可視化、監査CSVのダウンロード提供。

---

## 📂 ディレクトリ構成

```text
JPS_Refine_Studio/
├── 01_cleansing_studio/        # メタデータ精緻化 GUIアプリケーション (Streamlit)
│   ├── app.py                  # メインエントリポイント＆ルーティング
│   ├── run_fetch_worker.py     # バックグラウンド取得ワーカー (CLI)
│   ├── test_pipeline.py        # パイプライン総合テストスイート (全11テスト)
│   ├── components/             # UIコンポーネント (PillBoard, スタイル, ファイル/NDC操作)
│   ├── modules/                # コアロジック
│   │   ├── duckdb_manager.py       # DuckDB 高速管理・判定エンジン
│   │   ├── sparql_collector.py     # SPARQL 取得・ジョブ管理・マニフェスト
│   │   ├── workspace_manager.py    # ワークスペース・スナップショット統括
│   │   ├── rule_filter.py          # About/Type ルール・LLMサジェスト
│   │   ├── ngram_filter.py         # タイトル N-Gram マイニング
│   │   ├── llm_classifier.py       # マルチスレッド LLM セマンティック推論
│   │   ├── llm_query_expander.py   # LLM 検索語彙拡張・SPARQL生成
│   │   ├── review_portal.py        # 専門家査読フォールバックロジック
│   │   └── logger.py               # 統一ロガー
│   ├── rules/                  # ルールテンプレート (About, N-gram, Type)
│   └── views/                  # 各ステップの画面ビュー
│
├── 02_search_viewer/           # 検索・閲覧 Webフロントエンド (HTML/CSS/Vanilla JS)
│   ├── index.html              # ビューアUI (カタログ検索 ＆ PRISMA再現性パネル)
│   ├── style.css               # スタイル定義 (モダンUI・ダークモード対応)
│   ├── app.js                  # 検索・ファセット・チャート・PRISMA描画
│   ├── build_viewer_data.py    # 精緻化データからビューア用JSONを生成するスクリプト
│   └── scores_data.json        # 検索用データセット (Step 5で出力)
│
├── data/                       # 実行時データディレクトリ
│   ├── ndc_api_cache.json      # NDC API キャッシュ
│   ├── ndlna_api_cache.json    # NDLNA API キャッシュ
│   └── workspaces/             # 各研究テーマの作業空間
│       └── gagaku_default/     # デフォルトワークスペース (雅楽)
│           ├── workspace_meta.json # ワークスペース定義情報
│           ├── data/               # DuckDB, 生JSONL, 監査CSV等
│           ├── rules/              # ワークスペース固有ルール
│           ├── snapshots/          # 判定状態スナップショット (.parquet)
│           └── exports/            # 出力パッケージ
│
├── archive/                    # 過去データ資産・旧スクリプト退避アーカイブ
│   ├── data/                   # 過去に収集・精緻化された実データセット
│   ├── rules/                  # 過去の旧形式ルールファイル
│   └── scripts/                # 検証用スクリプト (ベンチマーク等)
│
├── docs/                       # 設計・改修ドキュメント (実装計画・ウォークスルー)
├── requirements.txt            # Python依存ライブラリ一覧
├── .gitignore                  # Git除外設定
└── README.md                   # 本ドキュメント
```

---

## 🚀 セットアップと利用手順

### 1. 動作環境の準備
Python 3.10 以上を推奨します。

```bash
# 仮想環境の作成とアクティベート
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 2. クレンジング・スタジオの起動
```bash
streamlit run 01_cleansing_studio/app.py
```
ブラウザが自動的に立ち上がり、`http://localhost:8501` でスタジオ画面が開きます。
サイドバーの「工程を選択」メニューから各ステップを進行できます。

### 3. バックグラウンド取得ワーカーの単独実行 (CLI)
長時間のメタデータ収集を行う場合、GUIからだけでなくコマンドラインから直接ワーカーを実行することも可能です：

```bash
python3 01_cleansing_studio/run_fetch_worker.py --workspace-id gagaku_default
```

### 4. パイプライン総合テストの実行
システムの全機能（LLMサジェスト、SPARQL生成、About/N-gram、DuckDBエンジン、レジューム、来歴追跡・PRISMA、ワークスペース管理、高速分割）を検証します：

```bash
python3 01_cleansing_studio/test_pipeline.py
```

### 5. 検索ビューアの起動
`02_search_viewer` は静的Webアプリケーションです。

```bash
cd 02_search_viewer
python3 -m http.server 8000
```
ブラウザで `http://localhost:8000` を開くことで、精緻化された楽譜データの検索・閲覧および PRISMA 絞り込みプロセスの追跡が可能です。
（※データが未エクスポートの場合は、スタジオの Step 5 を実行するか `python3 02_search_viewer/build_viewer_data.py` を実行してください。）
