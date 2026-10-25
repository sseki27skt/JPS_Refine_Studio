# JPS-Refine Studio (ジャパンサーチ・メタデータ精緻化＆検索スタジオ)

ジャパンサーチ（Japan Search）等の文化資源メタデータからノイズを高精度に除外・精緻化し、デジタルアーカイブとして活用するための統合研究・開発プラットフォームです。

「譜」という文字の多義性（家譜、年譜、画譜などの非音楽資料）を系統的に排除し、真正な「楽譜資料」を効率的に抽出・構造化するために開発されました。

---

## 🌟 主な特徴

1. **多段階ハイブリッド・クレンジングパイプライン (`01_cleansing_studio`)**
   - **Step 1: データ収集**: SPARQLクエリとLLMを活用した検索語彙拡張によるJapan Searchメタデータ自動取得
   - **Step 2-A: データ種別 (`rdf:type`) フィルタ**: 書誌種別に基づくノイズ除外
   - **Step 2-B: 主題 (`schema:about`) フィルタ**: NDC分類やNDLNA典拠データと連携した主題判定
   - **Step 2-C: タイトル語彙・N-gram フィルタ**: 頻出語・接尾辞・N-gramによる高速フィルタリング
   - **Step 3: LLMセマンティック判定**: 判定保留（グレーゾーン）のレコードに対するローカル/クラウドLLM推論
   - **Step 4: 専門家査読**: 人間による最終確認と手動オーバーライド
   - **Step 5: 統合出力**: 検索フロントエンド用JSON（`scores_data.json`）およびCSVへのエクスポート

2. **高速＆インタラクティブな検索ビューア (`02_search_viewer`)**
   - 精緻化されたメタデータを即座にブラウジング可能な静的Webアプリケーション
   - ジャンル（雅楽、能楽/謡曲、三味線音楽、尺八楽、琵琶楽、声明など）や演奏楽器、提供機関による絞り込み
   - Chart.js によるジャンル別・時代別の統計可視化
   - サーバーレスで動作（GitHub Pages 等にそのまま公開可能）

---

## 📂 ディレクトリ構成

```text
JPS-Refine Studio/
├── 01_cleansing_studio/        # メタデータ精緻化 GUIアプリケーション (Streamlit)
│   ├── app.py                  # メインエントリポイント
│   ├── .streamlit/             # UIテーマ・設定ファイル
│   ├── components/             # UIコンポーネント (PillBoard, スタイル等)
│   ├── modules/                # ロジック (SPARQL, フィルタ, LLM判定, ログ等)
│   ├── rules/                  # 蓄積された判定ルール (About, N-gram, Type, 語彙リスト)
│   └── views/                  # 各ステップの画面ビュー
│
├── 02_search_viewer/           # 検索・閲覧 Webフロントエンド (HTML/CSS/JS)
│   ├── index.html              # ビューアUI
│   ├── style.css               # スタイル定義
│   ├── app.js                  # 検索・フィルタリング・チャート描画ロジック
│   ├── build_viewer_data.py    # 確定データからビューア用JSONを生成するスクリプト
│   └── scores_data.json        # 検索用データセット
│
├── data/                       # ルール確定データ・APIキャッシュ・出力データ
│   ├── ndc_api_cache.json      # NDC API キャッシュ
│   ├── ndlna_api_cache.json    # NDLNA API キャッシュ
│   ├── confirmed_ok_rules.jsonl# 確定済み正例データ
│   ├── cleaned_metadata.csv    # 最新クレンジング済みCSV成果物
│   └── target_uris.csv         # 抽出対象URI一覧
│
├── docs/                       # 研究成果・論文ドラフト
│   └── jinmoncom_2026_paper/   # 人文科学とコンピュータシンポジウム論文草稿
│
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
サイドバーのメニューから各ステップを実行・確認できます。

### 3. 検索ビューアの起動
`02_search_viewer` は静的Webアプリケーションです。

```bash
# ローカルWebサーバーでプレビューする場合
cd 02_search_viewer
python3 -m http.server 8000
```
ブラウザで `http://localhost:8000` を開くことで、楽譜データの検索・閲覧が可能です。

---

## 📄 論文・研究関連
本プロジェクトに関する研究発表・論文草稿は `docs/jinmoncom_2026_paper/paper_draft.md` をご参照ください。
