# -*- coding: utf-8 -*-
"""
Japan Search メタデータ一括取得 バックグラウンド実行ワーカー
ブラウザから切り離して独立プロセスとして実行可能。
"""
import os
import sys
import argparse
import signal
import time
import json
import pandas as pd

# 親ディレクトリを sys.path に追加
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from modules.sparql_collector import (
    build_metadata_for_uris,
    update_job_status,
    get_job_status,
    is_process_alive,
    fetch_uris_with_query_func,
    DEFAULT_STATUS_FILE,
    save_acquisition_manifest,
    get_acquisition_manifest,
    DEFAULT_MANIFEST_FILE
)
from modules.llm_query_expander import generate_sparql_queries
from modules.duckdb_manager import DuckDBManager
from modules.logger import logger

ACTIVE_STATUS_FILE = DEFAULT_STATUS_FILE


_is_exiting = False

def handle_exit(signum, frame):
    """シグナル受信時にステータスを更新して安全に終了（多重再入防止）"""
    global _is_exiting
    if _is_exiting:
        return
    _is_exiting = True

    try:
        logger.info(f"[Worker] シグナル {signum} を受信。ジョブを中断ステータスに設定します...")
        print(f"[Worker] シグナル {signum} を受信。ジョブを中断ステータスに設定します...")
        update_job_status(status="STOPPED", error_message="シグナル受信によりプロセスが中断されました。", status_file=ACTIVE_STATUS_FILE)
    except Exception as e:
        logger.error(f"[Worker] 終了処理中のエラー: {e}")
    finally:
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Japan Search メタデータ取得 バックグラウンドワーカー")
    parser.add_argument("--workspace-id", type=str, default=None, help="対象ワークスペースID（指定時は各パスを自動解決）")
    parser.add_argument("--params-json", type=str, default=None, help="検索条件パラメータJSONパス（指定時はURI収集から全自動実行）")
    parser.add_argument("--target-uris", type=str, default=None, help="対象URIリスト(CSVまたはTXT)")
    parser.add_argument("--output-jsonl", type=str, default=None, help="出力先JSONLパス")
    parser.add_argument("--status-file", type=str, default=None, help="ステータス記録用JSONパス")
    parser.add_argument("--duckdb-path", type=str, default=None, help="同期先DuckDBパス")
    parser.add_argument("--batch-size", type=int, default=10, help="初期バッチサイズ")
    parser.add_argument("--no-resume", action="store_true", help="レジュームを無効化（最初から再取得）")
    parser.add_argument("--no-adaptive", action="store_true", help="適応型レート制御を無効化")
    parser.add_argument("--no-repair", action="store_true", help="自動修復を無効化")

    args = parser.parse_args()

    # ワークスペースパスの解決
    if args.workspace_id:
        from modules.workspace_manager import WorkspaceManager
        wm = WorkspaceManager()
        ws_paths = wm.get_workspace_paths(args.workspace_id)
        if not args.target_uris:
            args.target_uris = ws_paths["PATH_TARGET_URIS"]
        if not args.output_jsonl:
            args.output_jsonl = ws_paths["PATH_RAW_METADATA"]
        if not args.status_file:
            args.status_file = ws_paths["PATH_JOB_STATUS"]
        if not args.duckdb_path:
            args.duckdb_path = ws_paths["PATH_DUCKDB"]

    # デフォルトフォールバック
    if not args.target_uris:
        args.target_uris = os.path.join(CURRENT_DIR, "..", "data", "target_uris.csv")
    if not args.output_jsonl:
        args.output_jsonl = os.path.join(CURRENT_DIR, "..", "data", "raw_metadata.jsonl")
    if not args.status_file:
        args.status_file = DEFAULT_STATUS_FILE
    if not args.duckdb_path:
        args.duckdb_path = os.path.join(CURRENT_DIR, "..", "data", "metadata_store.duckdb")

    global ACTIVE_STATUS_FILE
    ACTIVE_STATUS_FILE = args.status_file


    # シグナルハンドラ設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    my_pid = os.getpid()

    # 二重起動チェック (排他制御)
    existing_st = get_job_status(args.status_file)
    prev_pid = existing_st.get("pid")
    if existing_st.get("status") == "RUNNING" and prev_pid and prev_pid != my_pid:
        if is_process_alive(prev_pid):
            logger.warning(f"[Worker PID={my_pid}] 既に別のワーカー (PID={prev_pid}) が実行中のため、二重起動を防止し終了します。")
            print(f"[Worker PID={my_pid}] 既に別のワーカー (PID={prev_pid}) が実行中のため、二重起動を防止し終了します。")
            sys.exit(0)

    logger.info(f"[Worker PID={my_pid}] バックグラウンドワーカー起動開始")
    print(f"[Worker PID={my_pid}] バックグラウンドワーカー起動開始")

    # --- Phase 1: params-json が指定されている場合はURI特定から全自動実行 ---
    if args.params_json and os.path.exists(args.params_json):
        logger.info(f"[Worker PID={my_pid}] パラメータJSONからURI網羅収集フェーズを開始: {args.params_json}")
        print(f"[Worker PID={my_pid}] パラメータJSONからURI網羅収集フェーズを開始: {args.params_json}")
        try:
            with open(args.params_json, 'r', encoding='utf-8') as f:
                exp_params = json.load(f)
            
            is_unlim = exp_params.get("is_unlimited", True)
            query_limit = exp_params.get("limit_val", 500)

            queries = generate_sparql_queries(exp_params)
            total_q_count = len(queries)
            all_uris_set = set()
            failed_queries = []

            update_job_status(
                status="RUNNING",
                stage="collect_uris",
                total_target=0,
                processed_count=0,
                pid=my_pid,
                status_file=args.status_file
            )

            for idx, (name, func) in enumerate(queries):
                # 中断チェック
                cur_st = get_job_status(args.status_file)
                if cur_st.get("status") in ["STOP_REQUESTED", "STOPPED"]:
                    update_job_status(status="STOPPED", error_message="ユーザー要求により中断", status_file=args.status_file)
                    sys.exit(0)

                logger.info(f"[{idx+1}/{total_q_count}] パターン実行中: {name} (limit={query_limit}, unlimited={is_unlim})")
                uris, success = fetch_uris_with_query_func(
                    func, 
                    pattern_name=name, 
                    limit=query_limit, 
                    unlimited=is_unlim, 
                    timeout_sec=45
                )
                all_uris_set.update(uris)
                if not success:
                    failed_queries.append((name, func))

                update_job_status(
                    stage=f"collect_uris ({idx+1}/{total_q_count} パターン)",
                    total_target=len(all_uris_set),
                    status_file=args.status_file
                )

            # 遅延パターンの再取得
            if failed_queries:
                time.sleep(3)
                for idx, (name, func) in enumerate(failed_queries):
                    uris, success = fetch_uris_with_query_func(
                        func, pattern_name=f"{name} (再試行)", limit=query_limit, unlimited=is_unlim, timeout_sec=60
                    )
                    all_uris_set.update(uris)

            # CSV 保存
            unique_uris = sorted(list(all_uris_set))
            os.makedirs(os.path.dirname(args.target_uris), exist_ok=True)
            df_uris = pd.DataFrame({"uri": unique_uris})
            df_uris.to_csv(args.target_uris, index=False, encoding='utf-8')
            logger.info(f"[Worker PID={my_pid}] 対象URI収集完了: {len(unique_uris):,} 件 ➔ {args.target_uris}")
            print(f"[Worker PID={my_pid}] 対象URI収集完了: {len(unique_uris):,} 件 ➔ {args.target_uris}")

            # 初期メタデータプール取得マニフェスト (Provenance) の保存
            sparql_samples = {}
            for name, func in queries:
                try:
                    sparql_samples[name] = func(100, 0)
                except Exception:
                    pass

            manifest_data = {
                "dataset_name": "Japan Search Cleansed Collection",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "endpoint": "https://jpsearch.go.jp/rdf/sparql/",
                "parameters": {
                    "keywords": exp_params.get("keywords", []),
                    "target_ndc": exp_params.get("ndc_codes", []),
                    "exclude_ndc": exp_params.get("exclude_ndc_codes", []),
                    "title_regex": exp_params.get("title_regex", ""),
                    "desc_regex": exp_params.get("desc_regex", ""),
                    "domain_definition": exp_params.get("domain_definition", "")
                },
                "sparql_queries": sparql_samples,
                "metrics": {
                    "total_target_uris": len(unique_uris),
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            manifest_path = os.path.join(os.path.dirname(args.output_jsonl), "acquisition_manifest.json")
            save_acquisition_manifest(manifest_data, manifest_path)

        except Exception as e:
            err = f"URI網羅収集フェーズでエラーが発生しました: {e}"
            logger.error(f"[Worker] {err}")
            update_job_status(status="FAILED", error_message=err, pid=my_pid, status_file=args.status_file)
            sys.exit(1)

    # 対象URIの読み込み
    target_uris = []
    if os.path.exists(args.target_uris):
        try:
            if args.target_uris.endswith(".csv"):
                df = pd.read_csv(args.target_uris)
                if 'uri' in df.columns:
                    target_uris = df['uri'].dropna().unique().tolist()
                elif len(df.columns) > 0:
                    target_uris = df.iloc[:, 0].dropna().unique().tolist()
            else:
                with open(args.target_uris, 'r', encoding='utf-8') as f:
                    target_uris = [line.strip() for line in f if line.strip()]
        except Exception as e:
            err = f"URIリストの読み込みに失敗しました: {e}"
            logger.error(f"[Worker] {err}")
            update_job_status(status="FAILED", error_message=err, pid=my_pid, status_file=args.status_file)
            sys.exit(1)

    if not target_uris:
        err = f"対象URIが0件です: {args.target_uris}"
        logger.error(f"[Worker] {err}")
        update_job_status(status="FAILED", error_message=err, pid=my_pid, status_file=args.status_file)
        sys.exit(1)

    unique_uris = sorted(list(set(target_uris)))
    logger.info(f"[Worker PID={my_pid}] 対象URI数: {len(unique_uris):,} 件")
    print(f"[Worker PID={my_pid}] 対象URI数: {len(unique_uris):,} 件")

    # 初期ステータス記録
    update_job_status(
        status="RUNNING",
        stage="build_metadata",
        total_target=len(unique_uris),
        processed_count=0,
        current_batch_size=args.batch_size,
        pid=my_pid,
        status_file=args.status_file
    )

    # DuckDBマネージャーの初期化
    duck_mgr = None
    if args.duckdb_path:
        try:
            os.makedirs(os.path.dirname(args.duckdb_path), exist_ok=True)
            duck_mgr = DuckDBManager(db_path=args.duckdb_path)
        except Exception as e:
            logger.warning(f"[Worker] DuckDBマネージャー初期化スキップ: {e}")

    # 取得処理実行
    manifest_path = os.path.join(os.path.dirname(args.output_jsonl), "acquisition_manifest.json")
    try:
        build_metadata_for_uris(
            uri_list=unique_uris,
            output_jsonl_path=args.output_jsonl,
            batch_size=args.batch_size,
            auto_repair=not args.no_repair,
            resume=not args.no_resume,
            adaptive=not args.no_adaptive,
            status_file=args.status_file,
            duckdb_manager=duck_mgr,
            manifest_file=manifest_path
        )
        logger.info(f"[Worker PID={my_pid}] 取得処理が正常に完了しました。")
        print(f"[Worker PID={my_pid}] 取得処理が正常に完了しました。")
    except Exception as e:
        err = f"メタデータ取得中に致命的エラーが発生しました: {e}"
        logger.error(f"[Worker] {err}")
        update_job_status(status="FAILED", error_message=err, pid=my_pid, status_file=args.status_file)
        sys.exit(1)
    finally:
        if duck_mgr:
            duck_mgr.close()


if __name__ == "__main__":
    main()
