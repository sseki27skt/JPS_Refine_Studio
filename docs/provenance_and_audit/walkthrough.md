# メタデータ構築・絞り込みプロセスの再現性 ＆ 追跡可能性（Provenance & Audit）実装完了ウォークスルー

## 1. 概要と学術的背景

本実装は、Japan Search から構築される古典籍楽譜メタデータセットを**学術的な研究成果（査読付き論文・公式デジタルアーカイブポータル）として外部公開する**にあたり、初期母集団の抽出条件から多段階クレンジングパイプラインによる判定過程までの**完全な再現性 (Reproducibility)** および **追跡可能性 (Traceability / Data Provenance)** を担保・検証できるようにしたものです。

これにより、外部の第三者研究者が：
1. **「どういう条件で初期母集団が集められたのか」**（SPARQLクエリ、キーワード、NDC分類、正規表現）
2. **「どのレコードが、どの段階で、どのような理由・根拠（Type / About NDC / N-gram / LLM推論 / 専門家査読）で採否決定されたのか」**（Audit Trail CSV）
3. **「全体として何件が各ステップで脱落したのか」**（系統的レビュー PRISMA 2020 準拠フローレポート）
4. **「公開ポータルで合格資料を検索する際、各資料がどのような根拠で真正楽譜として認められたのか」**（検索ビューアでの一体提示）

を完全に検証できるようになりました。

---

## 2. 実装された機能とコンポーネント

### Phase 1: 記録スキーマとデータ構造の設計
- **DuckDB 来歴カラムの拡張**: `01_cleansing_studio/modules/duckdb_manager.py`
  - `metadata_records` テーブルに以下の追跡用カラムを追加：
    - `type_reason`: Typeフィルタ除外時のマッチした `rdf:type`
    - `about_reason`: NDC/NDLNA分類コードに基づく合否理由
    - `ngram_reason`: タイトル語彙・接尾辞に基づく合否理由
    - `adopted_stage`: 最終採択された段階（`RULE`, `LLM`, `HUMAN`）
    - `drop_stage`: 除外された段階（`TYPE`, `RULE`, `LLM`, `HUMAN`）
    - `primary_reason`: 最終的な合否を決定づけた主要理由
  - 高速検索用インデックス（`idx_records_drop`, `idx_records_adopted`）を自動作成。

### Phase 2: 初期メタデータプール取得条件の完全マニフェスト化 (Step 1)
- **マニフェスト生成モジュール**: `01_cleansing_studio/modules/sparql_collector.py`
  - `save_acquisition_manifest()`, `get_acquisition_manifest()` を実装。
  - SPARQLクエリ全文、拡張キーワード、対象NDC（包含・除外）、正規表現、取得日時、URI総数・成功数を記録した `data/acquisition_manifest.json` を自動保存。
- **UI表示**: `01_cleansing_studio/views/step1_fetch_view.py`
  - 画面下部に「📋 初期メタデータプール取得条件マニフェスト」確認エキスパンダーを配置。

### Phase 3: 段階的フィルタリング判定理由の完全追跡 (Step 2〜4)
- **判定理由の記録と上書き防止**:
  - `apply_type_filter_fast()`: 該当しない `rdf:type`（記事、公演等）を検知し、`type_status='NG'`, `drop_stage='TYPE'`, `primary_reason` を記録。
  - `apply_rules_fast()`: **Type除外されたレコードが後続のルール判定で上書きされない保護ロジック**を実装。About（NDC分類）および N-gram（形態素・接尾辞）の判定理由をレコード単位で保持。
  - `sync_llm_judgments()`: LLM推論結果・判定理由・確信度を DuckDB へ同期。
  - `set_human_decision()`: 専門家による手動オーバーライド時、`human_decision`, `review_reasons`, `adopted_stage='HUMAN'` を即時反映。

### Phase 4: 学術成果物出力パッケージの拡充 (Step 5)
- **3大成果物の一括生成**: `01_cleansing_studio/views/step3_export_view.py`
  1. `scores_data.json`: 公開検索ビューア用データ。各資料に `provenance: {stage, reason, confidence}` を付与。
  2. `complete_audit_trail.csv`: 母集団全件（十数万件）の判定段階・判定理由・合否結果を網羅した監査シート。
  3. `prisma_flow_report.md` / `prisma_flow_summary.json`: 系統的レビュー標準（PRISMA 2020）準拠のフロー図（Mermaid）・段階別集計テーブル・除外理由ランキング。

### Phase 5: 公開用検索ビューア（`02_search_viewer`）での結果・過程の一体提示
- **ナビゲーションタブの導入**: `index.html`, `style.css`
  - 「📚 資料カタログ検索」と「📊 絞り込みプロセス ＆ 再現性（PRISMA）」のタブ切り替え。
- **採択根拠の可視化**: `app.js`
  - 検索カードに「🏷️ 採択: ルール判定 (About/N-gram)」バッジを動的表示。
  - 詳細モーダル内に「✅ 採択根拠（Provenance）」ボックスを表示（ステージ・理由・確信度）。
- **再現性検証パネル**:
  - 初期母集団の抽出条件（キーワード、包含NDC、除外NDC、正規表現）をリアルタイム表示。
  - PRISMA脱落フロー図（初期同定 ➔ Type除外 ➔ ルール除外 ➔ LLM除外 ➔ 最終採択）。
  - 主な除外理由ランキング（非音楽資料の系統的排除内訳）。
  - 完全追跡CSV（`complete_audit_trail.csv`）およびマニフェスト（`acquisition_manifest.json`）のダウンロードボタンを設置。

---

## 3. 検証結果

### 1. パイプライン総合テスト (`01_cleansing_studio/test_pipeline.py`)
`test_pipeline.py` に追加した新設テスト `[Test 10] Provenance & Audit Trail Integration Test` を含む全10工程を実行し、すべて正常通過（Exit Code: 0）しました。

- **Test 1**: 高速LLMサジェスト (0.00s)
- **Test 2**: クエリ拡張テスト
- **Test 3**: SPARQLクエリ生成テスト (4パターン)
- **Test 4**: Schema:About 抽出・フィルタ
- **Test 5**: N-Gram 抽出・フィルタ
- **Test 6**: 専門家査読ポータルデータ統合
- **Test 7**: マルチスレッド推論
- **Test 8**: DuckDB 高速エンジン
- **Test 9**: レジューム・ジョブ管理
- **Test 10**: **Provenance & Audit Trail 統合テスト (マニフェスト保存・Type除外・ルール除外・PRISMA統計・Audit Trail CSV出力全件検証)**

### 2. データ生成・成果物出力検証 (`build_viewer_data.py` & `test_viewer_data.js`)
- DuckDB（158,189件の母集団）および JSONL から `02_search_viewer/scores_data.json`（10,000件）を生成。
- `data/complete_audit_trail.csv`（20.54MB）が生成され、全レコードの採否判定理由が保持されていることを確認。
- `data/prisma_flow_summary.json` および `data/acquisition_manifest.json` が正常に生成され、ビューア側でのパース・連携が成功。

---

## 4. 今後の運用と保守

1. **実データ取得時**:
   - Step 1 の「深層メタデータ取得」を実行すると、自動的に `data/acquisition_manifest.json` が生成・更新されます。
2. **多段階クレンジング時**:
   - Step 2〜4 を進行する際、DuckDB が自動的に `type_reason`, `about_reason`, `ngram_reason`, `adopted_stage`, `drop_stage` を追跡記録します。
3. **成果物公開時**:
   - Step 5 で「学術研究パッケージの一括生成」を実行するか、`python3 02_search_viewer/build_viewer_data.py` を実行するだけで、論文掲載用レポートと公開ポータル用データが一括で整います。
