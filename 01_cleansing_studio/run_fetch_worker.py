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
import pandas as pd

# 親ディレクトリを sys.path に追加
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from modules.sparql_collector import (
    build_metadata_for_uris,
    update_job_status,
    get_job_status,
    DEFAULT_STATUS_FILE
)
from modules.duckdb_manager import DuckDBManager
from modules.logger import logger


def handle_exit(signum, frame):
    """シグナル受信時にステータスを更新して安全に終了"""
    logger.info(f"[Worker] シグナル {signum} を受信。ジョブを中断ステータスに設定します...")
    update_job_status(status="STOPPED", error_message="シグナル受信によりプロセスが中断されました。")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Japan Search メタデータ取得 バックグラウンドワーカー")
    parser.add_argument("--target-uris", type=str, default=os.path.join(CURRENT_DIR, "..", "data", "target_uris.csv"), help="対象URIリスト(CSVまたはTXT)")
    parser.add_argument("--output-jsonl", type=str, default=os.path.join(CURRENT_DIR, "..", "data", "raw_metadata.jsonl"), help="出力先JSONLパス")
    parser.add_argument("--status-file", type=str, default=DEFAULT_STATUS_FILE, help="ステータス記録用JSONパス")
    parser.add_argument("--duckdb-path", type=str, default=os.path.join(CURRENT_DIR, "..", "data", "metadata_store.duckdb"), help="同期先DuckDBパス")
    parser.add_argument("--batch-size", type=int, default=10, help="初期バッチサイズ")
    parser.add_argument("--no-resume", action="store_true", help="レジュームを無効化（最初から再取得）")
    parser.add_argument("--no-adaptive", action="store_true", help="適応型レート制御を無効化")
    parser.add_argument("--no-repair", action="store_true", help="自動修復を無効化")

    args = parser.parse_args()

    # シグナルハンドラ設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    my_pid = os.getpid()
    logger.info(f"[Worker PID={my_pid}] バックグラウンドワーカー起動開始")
    print(f"[Worker PID={my_pid}] バックグラウンドワーカー起動開始")

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
    try:
        build_metadata_for_uris(
            uri_list=unique_uris,
            output_jsonl_path=args.output_jsonl,
            batch_size=args.batch_size,
            auto_repair=not args.no_repair,
            resume=not args.no_resume,
            adaptive=not args.no_adaptive,
            status_file=args.status_file,
            duckdb_manager=duck_mgr
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
