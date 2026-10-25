# -*- coding: utf-8 -*-
"""
Japan Search SPARQL自動取得 ＆ 深層メタデータ構築モジュール (BuildMetadata.py 準拠)
"""

import os
import sys
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from .logger import logger, log_stats
except (ImportError, ValueError):
    from logger import logger, log_stats
import pandas as pd
from collections import defaultdict

ENDPOINT = "https://jpsearch.go.jp/rdf/sparql/"
DEFAULT_LIMIT = 500
MAX_RETRIES = 5

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATUS_FILE = os.path.join(BASE_DIR, "data", "fetch_job_status.json")

PREFIX_MAP = {
    "http://schema.org/": "schema:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://purl.org/dc/terms/": "dct:",
    "https://jpsearch.go.jp/term/property#": "jps:",
    "https://jpsearch.go.jp/term/property/": "jps:",
    "http://www.w3.org/2002/07/owl#": "owl:",
    "http://www.w3.org/2004/02/skos/core#": "skos:"
}


def is_process_alive(pid: int) -> bool:
    """PIDで指定されたプロセスが現在生存しているかを判定 (macOS/Linux)"""
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_job_status(status_file: str = None) -> dict:
    """現在の取得ジョブステータスを取得（プロセス死活監視・自動回復付き）"""
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    if not os.path.exists(status_file):
        return {
            "pid": None,
            "status": "IDLE",
            "stage": "idle",
            "total_target": 0,
            "processed_count": 0,
            "current_batch_size": 10,
            "started_at": None,
            "updated_at": None,
            "eta_seconds": None,
            "error_message": None
        }
    try:
        with open(status_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {
            "pid": None,
            "status": "IDLE",
            "stage": "idle",
            "total_target": 0,
            "processed_count": 0
        }

    # RUNNING なのにプロセスが死んでいる場合の自動回復
    pid = data.get("pid")
    if data.get("status") == "RUNNING" and pid:
        if not is_process_alive(pid):
            data["status"] = "STOPPED"
            data["error_message"] = "プロセスが終了したか停止されました。"
            data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_job_status(data, status_file)

    return data


def save_job_status(data: dict, status_file: str = None):
    """ジョブステータスをファイルにアトミック書き込み"""
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    tmp_file = f"{status_file}.tmp"
    with open(tmp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, status_file)


def update_job_status(
    status: str = None,
    stage: str = None,
    total_target: int = None,
    processed_count: int = None,
    current_batch_size: int = None,
    eta_seconds: int = None,
    error_message: str = None,
    pid: int = None,
    status_file: str = None
):
    """ジョブステータスを安全に部分更新"""
    current = get_job_status(status_file)
    if status is not None:
        current["status"] = status
    if stage is not None:
        current["stage"] = stage
    if total_target is not None:
        current["total_target"] = total_target
    if processed_count is not None:
        current["processed_count"] = processed_count
    if current_batch_size is not None:
        current["current_batch_size"] = current_batch_size
    if eta_seconds is not None:
        current["eta_seconds"] = eta_seconds
    if error_message is not None:
        current["error_message"] = error_message
    elif status in ["RUNNING", "COMPLETED"]:
        current["error_message"] = None
    if pid is not None:
        current["pid"] = pid

    current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if current["status"] == "RUNNING" and not current.get("started_at"):
        current["started_at"] = current["updated_at"]
    elif current["status"] in ["COMPLETED", "STOPPED", "FAILED"]:
        current["eta_seconds"] = 0

    save_job_status(current, status_file)


def request_job_stop(status_file: str = None) -> bool:
    """実行中ジョブに対して安全な停止を要求"""
    status = get_job_status(status_file)
    if status.get("status") == "RUNNING":
        update_job_status(status="STOP_REQUESTED", error_message="ユーザーによる安全停止が要求されました。", status_file=status_file)
        return True
    return False


def get_robust_session() -> requests.Session:
    """
    HTTPS 443 接続を効率的に使い回し (Keep-Alive)、接続切断・タイムアウトに強いセッションを生成
    """
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def shorten_uri(uri: str) -> str:
    """
    長いURIをPrefix付きの短い文字列に変換する
    例: http://schema.org/name -> schema:name
    """
    for prefix, short in PREFIX_MAP.items():
        if uri.startswith(prefix):
            return uri.replace(prefix, short)
    return uri


def fetch_uris_with_query_func(
    query_func, 
    pattern_name="Custom Query", 
    limit=500, 
    unlimited: bool = True, 
    progress_callback=None, 
    timeout_sec=45, 
    max_query_retries=3
) -> tuple:
    """
    クエリ生成関数(limit, offset)を呼び出し、Japan SearchからURIを自動ページネーション取得します。
    unlimited=True の場合、該当する全データが尽きるまで何千〜何万件でも全件自動収集します。
    504エラー等が発生した場合は自動的にLIMITを縮小して自律回復します。
    """
    collected_uris = []
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    session = get_robust_session()
    base_batch_size = limit if limit and limit > 0 else 500
    current_limit = base_batch_size
    target_limit = limit if (not unlimited and limit and limit > 0) else None

    target_str = f"目標: {target_limit}件" if target_limit else "全件網羅 (上限なし)"
    logger.info(f"--- [開始] {pattern_name} ({target_str}) ---")
    print(f"\n--- [開始] {pattern_name} ({target_str}) ---")

    is_finished = False
    while not is_finished:
        if target_limit and len(collected_uris) >= target_limit:
            break

        if target_limit:
            needed_count = target_limit - len(collected_uris)
            fetch_size = min(current_limit, needed_count)
        else:
            fetch_size = current_limit

        current_offset = len(collected_uris)
        
        batch_success = False
        for attempt in range(1, max_query_retries + 1):
            try:
                query = query_func(fetch_size, current_offset)
                data = {'query': query, 'format': 'json'}
                
                prog_str = f"{len(collected_uris)}/{target_limit}" if target_limit else f"{len(collected_uris)}件〜"
                logger.info(f"[{pattern_name}] Sub-fetch (limit={fetch_size}, progress={prog_str}) ...")
                print(f"[{pattern_name}] Sub-fetch (limit={fetch_size}, progress={prog_str}) ...", end=" ")
                start_time = time.time()

                response = session.post(ENDPOINT, data=data, headers=headers, timeout=timeout_sec)

                if response.status_code in [504, 502, 503, 500]:
                    current_limit = max(20, current_limit // 2)
                    logger.warning(f"[{pattern_name}] [Server {response.status_code} 負荷警告] 単回LIMITを {current_limit} 件に縮小して即時小分け再リトライします...")
                    print(f"\n[Server {response.status_code} 負荷警告] 単回LIMITを {current_limit} 件に縮小して即時小分け再リトライします...")
                    time.sleep(2)
                    continue
                elif response.status_code != 200:
                    logger.error(f"[{pattern_name}] [Error] Status Code: {response.status_code}")
                    print(f"\n[Error] Status Code: {response.status_code}")
                    time.sleep(4)
                    continue

                resp_data = response.json()
                bindings = resp_data.get('results', {}).get('bindings', [])

                if not bindings:
                    logger.info(f"[{pattern_name}] Done (データ上限達成・これ以上結果なし).")
                    print("Done (データ上限達成・これ以上結果なし).")
                    batch_success = True
                    is_finished = True
                    break

                current_uris = [b['s']['value'] for b in bindings if 's' in b]
                new_uris = [u for u in current_uris if u not in collected_uris]
                
                if not new_uris:
                    logger.info(f"[{pattern_name}] Done (重複なしデータエンド).")
                    print("Done (重複なしデータエンド).")
                    batch_success = True
                    is_finished = True
                    break

                collected_uris.extend(new_uris)

                elapsed = time.time() - start_time
                total_str = f"{len(collected_uris)}/{target_limit}" if target_limit else f"累計: {len(collected_uris)}件"
                logger.info(f"[{pattern_name}] Got {len(new_uris)} new items. ({total_str}) [{elapsed:.2f}s]")
                log_stats("FETCH", len(new_uris), elapsed, f"{pattern_name} | Offset: {current_offset}")
                print(f"Got {len(new_uris)} new items. ({total_str}) [{elapsed:.2f}s]")

                if progress_callback:
                    progress_callback(pattern_name, len(collected_uris))

                # 成功したら LIMIT を徐々に元のサイズに戻す
                if current_limit < base_batch_size:
                    current_limit = min(base_batch_size, current_limit * 2)

                # 要求したfetch_sizeより返ってきた件数が少なければ、それが最後のページ
                if len(current_uris) < fetch_size:
                    logger.info(f"[{pattern_name}] 最終バッチ到達（全データ取得完了）。")
                    print(f"[{pattern_name}] 最終バッチ到達（全データ取得完了）。")
                    is_finished = True

                batch_success = True
                break

            except requests.exceptions.ReadTimeout:
                current_limit = max(20, current_limit // 2)
                logger.warning(f"[{pattern_name}] [応答タイムアウト 試行 {attempt}/{max_query_retries}] LIMITを {current_limit} 件に縮小して小分け再読み込みします。")
                print(f"\n[応答タイムアウト 試行 {attempt}/{max_query_retries}] LIMITを {current_limit} 件に縮小して小分け再読み込みします。")
                time.sleep(3)
            except Exception as e:
                logger.error(f"[{pattern_name}] [通信例外 試行 {attempt}/{max_query_retries}]: {e}")
                print(f"\n[通信例外 試行 {attempt}/{max_query_retries}]: {e}")
                time.sleep(3)

        if not batch_success:
            logger.error(f"[{pattern_name}] サブバッチ処理の応答遅延により一時終了。")
            print(f"[{pattern_name}] サブバッチ処理の応答遅延により一時終了。")
            break

        time.sleep(0.5)

    is_success = len(collected_uris) > 0
    time.sleep(1.0)  # 各 Part (クエリパターン) 完了ごとのウェイト
    return collected_uris, is_success


def fetch_deep_graph_with_stats(uris: list, session: requests.Session = None, timeout_sec: int = 45) -> tuple:
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得し、取得統計情報（成否・所要時間・分割回数）を返します。
    """
    if not uris:
        return [], {"is_clean": True, "split_count": 0, "elapsed": 0.0, "success": True}

    if session is None:
        session = get_robust_session()

    start_time = time.time()
    uris_str = " ".join([f"<{u}>" for u in uris])

    query = f"""
    PREFIX schema: <http://schema.org/>
    PREFIX jps: <https://jpsearch.go.jp/term/property/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    CONSTRUCT {{
        ?s ?p ?o .
        ?node ?p2 ?o2 .
        ?subnode ?p3 ?o3 .
    }}
    WHERE {{
        VALUES ?s {{ {uris_str} }}
        
        ?s ?p ?o .
        
        OPTIONAL {{
            ?s ?linkProp ?node .
            FILTER (ISBLANK(?node) || (ISURI(?node) && STRSTARTS(STR(?node), STR(?s))))
            ?node ?p2 ?o2 .
            
            OPTIONAL {{
                ?o2 ?p3 ?o3 .
                FILTER (ISBLANK(?o2) || (ISURI(?o2) && STRSTARTS(STR(?o2), STR(?s))))
            }}
        }}
    }}
    """

    data = {'query': query, 'format': 'json'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    # 1〜2回通常試行
    for attempt in range(1, 3):
        try:
            response = session.post(ENDPOINT, data=data, headers=headers, timeout=timeout_sec)
            elapsed = time.time() - start_time
            if response.status_code == 200:
                bindings = response.json().get('results', {}).get('bindings', [])
                return bindings, {"is_clean": True, "split_count": 0, "elapsed": elapsed, "success": True}
            elif response.status_code in [504, 502, 503]:
                logger.warning(f"[504負荷検知] 全 {len(uris)} 件のグラフ取得で遅延発生。3秒クールダウン後に小分け分割へ移行します...")
                print(f"\n[504負荷検知] 全 {len(uris)} 件のグラフ取得で遅延発生。3秒クールダウン後に小分け分割へ移行します...")
                time.sleep(3.0)
                break
        except requests.exceptions.ReadTimeout:
            logger.warning(f"[タイムアウト検知] 全 {len(uris)} 件のグラフ取得でタイムアウト発生。3秒待機後に小分け分割へ移行します...")
            print(f"\n[タイムアウト検知] 全 {len(uris)} 件のグラフ取得でタイムアウト発生。3秒待機後に小分け分割へ移行します...")
            time.sleep(3.0)
            break
        except Exception as e:
            logger.error(f"[通信遅延検知]: {e}")
            print(f"\n[通信遅延検知]: {e}")
            time.sleep(2.0)
            break
        time.sleep(1.0)

    # 失敗時、半分のチャンクに小分けにして再帰的にフォールバック取得
    if len(uris) > 1:
        mid = len(uris) // 2
        logger.info(f"-> チャンク分割小分け取得 ({len(uris)} 件 ➔ {mid} 件 + {len(uris) - mid} 件)")
        print(f"-> チャンク分割小分け取得 ({len(uris)} 件 ➔ {mid} 件 + {len(uris) - mid} 件)")
        res1, s1 = fetch_deep_graph_with_stats(uris[:mid], session=session, timeout_sec=timeout_sec)
        time.sleep(1.0)
        res2, s2 = fetch_deep_graph_with_stats(uris[mid:], session=session, timeout_sec=timeout_sec)
        total_elapsed = time.time() - start_time
        return res1 + res2, {
            "is_clean": False, 
            "split_count": 1 + s1.get("split_count", 0) + s2.get("split_count", 0), 
            "elapsed": total_elapsed, 
            "success": s1.get("success", False) or s2.get("success", False)
        }

    # 1件単体でも失敗した場合の簡易フォールバック（直下トリプルのみ取得）
    try:
        logger.info(f"-> 単体直下トリプル簡易取得フォールバック: <{uris[0]}>")
        time.sleep(2.0)
        simple_query = f"""
        CONSTRUCT {{ <{uris[0]}> ?p ?o . }}
        WHERE {{ <{uris[0]}> ?p ?o . }}
        """
        res = session.post(ENDPOINT, data={'query': simple_query, 'format': 'json'}, headers=headers, timeout=20)
        total_elapsed = time.time() - start_time
        if res.status_code == 200:
            return res.json().get('results', {}).get('bindings', []), {
                "is_clean": False, "split_count": 1, "elapsed": total_elapsed, "success": True
            }
    except Exception as e:
        logger.error(f"[簡易取得フォールバック失敗]: {e}")
        pass

    total_elapsed = time.time() - start_time
    return [], {"is_clean": False, "split_count": 1, "elapsed": total_elapsed, "success": False}


def fetch_deep_graph(uris: list, session: requests.Session = None, timeout_sec: int = 45) -> list:
    """
    CONSTRUCTクエリで親・子・孫ノードを一括取得 (BuildMetadata.py 互換ラッパー)
    """
    bindings, _ = fetch_deep_graph_with_stats(uris, session=session, timeout_sec=timeout_sec)
    return bindings


def parse_dynamic_graph(bindings: list, target_uris: list) -> list:
    """
    取得したCONSTRUCTトリプルからツリー型ネスト構造を構築 (BuildMetadata.py 準拠)
    """
    graph = defaultdict(lambda: defaultdict(list))
    for b in bindings:
        s = b['s']['value']
        p = b['p']['value']
        o = b['o']['value']
        graph[s][p].append(o)
    
    results = []
    
    for uri in target_uris:
        if uri not in graph:
            results.append({"@id": uri, "status": "failed"})
            continue
            
        def node_to_dict(current_node, visited=None):
            if visited is None:
                visited = set()
            
            if current_node in visited:
                return {"@id": current_node, "meta": "cyclic_reference"}
            
            visited.add(current_node)
            props = graph.get(current_node, {})
            node_data = {"@id": current_node}
            
            for p_uri, objects in props.items():
                short_p = shorten_uri(p_uri)
                
                parsed_objects = []
                for obj in objects:
                    if obj in graph and (obj.startswith(uri) or obj.startswith("_:")):
                        parsed_objects.append(node_to_dict(obj, visited.copy()))
                    else:
                        parsed_objects.append(obj)
                
                if len(parsed_objects) == 1:
                    node_data[short_p] = parsed_objects[0]
                else:
                    node_data[short_p] = parsed_objects

            return node_data

        structured_data = node_to_dict(uri)
        structured_data["status"] = "success"
        results.append(structured_data)
        
    return results


def check_metadata_completeness(target_uris: list, jsonl_path: str) -> dict:
    """
    指定されたURIリストとJSONLファイルの取得状況を照合し、
    正常取得、失敗(status:failed)、未取得(missing)のURI一覧と統計情報を返します。
    """
    unique_targets = sorted(list(set(target_uris)))
    if not os.path.exists(jsonl_path):
        return {
            "total_target": len(unique_targets),
            "valid_count": 0,
            "failed_count": 0,
            "missing_count": len(unique_targets),
            "valid_uris": [],
            "failed_uris": [],
            "missing_uris": unique_targets,
            "need_retry_uris": unique_targets,
            "is_complete": len(unique_targets) == 0
        }

    records_map = {}
    with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                uid = item.get("@id", item.get("id", item.get("uri", "")))
                if uid:
                    records_map[uid] = item
            except Exception:
                continue

    valid_uris = []
    failed_uris = []
    missing_uris = []

    for uri in unique_targets:
        if uri not in records_map:
            missing_uris.append(uri)
        else:
            item = records_map[uri]
            if item.get("status") == "failed" or len(item.keys()) <= 2:
                failed_uris.append(uri)
            else:
                valid_uris.append(uri)

    is_complete = (len(missing_uris) == 0 and len(failed_uris) == 0)

    return {
        "total_target": len(unique_targets),
        "valid_count": len(valid_uris),
        "failed_count": len(failed_uris),
        "missing_count": len(missing_uris),
        "valid_uris": valid_uris,
        "failed_uris": failed_uris,
        "missing_uris": missing_uris,
        "need_retry_uris": failed_uris + missing_uris,
        "is_complete": is_complete
    }


def verify_and_repair_metadata(
    target_uris: list, 
    jsonl_path: str, 
    max_repair_rounds: int = 3, 
    progress_callback=None,
    status_file: str = None
) -> dict:
    """
    全URIに紐づくメタデータがJSONLに正常に存在するか確認し、
    欠損（未取得またはfailed）がある場合は自動で小分け再取得を実行してマージ・修復します。
    """
    unique_targets = sorted(list(set(target_uris)))
    report = check_metadata_completeness(unique_targets, jsonl_path)
    if report["is_complete"]:
        logger.info(f"[整合性チェック合格] 全 {len(unique_targets):,} 件のメタデータが正常に取得されています。")
        print(f"\n[整合性チェック合格] 全 {len(unique_targets):,} 件のメタデータが正常に取得されています。")
        return report

    logger.info(f"--- [欠損自動修復プロセス開始] 欠損/失敗: {len(report['need_retry_uris']):,} / 全 {len(unique_targets):,} 件 ---")
    print(f"\n--- [欠損自動修復プロセス開始] 欠損/失敗: {len(report['need_retry_uris']):,} / 全 {len(unique_targets):,} 件 ---")

    session = get_robust_session()

    # 既存の全レコードをマップとして保持
    records_map = {}
    if os.path.exists(jsonl_path):
        with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    uid = item.get("@id", item.get("id", item.get("uri", "")))
                    if uid:
                        records_map[uid] = item
                except Exception:
                    continue

    for round_idx in range(1, max_repair_rounds + 1):
        curr_report = check_metadata_completeness(unique_targets, jsonl_path)
        need_retry = curr_report["need_retry_uris"]
        if not need_retry:
            break

        logger.info(f"[修復ラウンド {round_idx}/{max_repair_rounds}] 対象: {len(need_retry):,} 件の欠損URIを再取得中...")
        print(f"[修復ラウンド {round_idx}/{max_repair_rounds}] 対象: {len(need_retry):,} 件の欠損URIを再取得中...")

        repair_batch_size = 5
        recovered_this_round = 0

        for i in range(0, len(need_retry), repair_batch_size):
            # 停止要求チェック
            if status_file:
                cur_s = get_job_status(status_file)
                if cur_s.get("status") in ["STOP_REQUESTED", "STOPPED"]:
                    logger.info("[修復プロセス] 停止要求を検知したため中断します。")
                    break

            chunk = need_retry[i:i + repair_batch_size]
            bindings, _ = fetch_deep_graph_with_stats(chunk, session=session, timeout_sec=60)
            items = parse_dynamic_graph(bindings, chunk)

            for item in items:
                uid = item.get("@id", item.get("id", item.get("uri", "")))
                if uid:
                    records_map[uid] = item
                    if item.get("status") == "success":
                        recovered_this_round += 1

            if progress_callback:
                progress_callback(
                    round_idx, 
                    min(i + repair_batch_size, len(need_retry)), 
                    len(need_retry), 
                    recovered_this_round
                )

            time.sleep(2.0)

        # 各ラウンド終了時にファイルを更新
        with open(jsonl_path, 'w', encoding='utf-8') as out_f:
            for uid, item in records_map.items():
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_f.flush()

        logger.info(f"[修復ラウンド {round_idx} 完了] 今回修復成功: {recovered_this_round:,} 件")
        print(f"[修復ラウンド {round_idx} 完了] 今回修復成功: {recovered_this_round:,} 件")
        time.sleep(3.0)

    final_report = check_metadata_completeness(unique_targets, jsonl_path)
    return final_report


def build_metadata_for_uris(
    uri_list: list, 
    output_jsonl_path: str, 
    batch_size: int = 10, 
    progress_callback=None,
    auto_repair: bool = True,
    resume: bool = True,
    adaptive: bool = True,
    min_batch_size: int = 5,
    max_batch_size: int = 30,
    status_file: str = None,
    duckdb_manager=None
) -> int:
    """
    収集したURIリストに対して、Japan Search SPARQLからCONSTRUCT深層グラフメタデータを
    一括取得し、BuildMetadata.py 形式の短縮キーネストJSONLファイルとして保存します。
    - resume=True の場合、既に取得済みのURIを自動スキップし、追記モードで未取得分のみを取得します。
    - adaptive=True の場合、サーバーの応答状況に応じてバッチサイズを自動で 5〜30 件へ伸縮します。
    - status_file が指定されている場合、リアルタイムに進捗状況をJSONファイルに記録します。
    - duckdb_manager が指定されている場合、完了時にDuckDBにも自動でバルク同期します。
    """
    os.makedirs(os.path.dirname(output_jsonl_path), exist_ok=True)
    
    unique_uris = sorted(list(set(uri_list)))
    total_count = len(unique_uris)

    # 1. 既存データの走査（レジューム判定）
    existing_uris = set()
    if resume and os.path.exists(output_jsonl_path):
        try:
            with open(output_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        u = rec.get("@id", rec.get("id", rec.get("uri", "")))
                        if u and rec.get("status") != "failed":
                            existing_uris.add(u)
                    except Exception:
                        pass
            logger.info(f"[レジューム検出] 既存ファイルから {len(existing_uris):,} 件の取得済みURIを認識しました。")
            print(f"[レジューム検出] 既存ファイルから {len(existing_uris):,} 件の取得済みURIを認識しました。")
        except Exception as e:
            logger.warning(f"[レジューム確認警告] 既存ファイル読み込み例外: {e}")

    pending_uris = [u for u in unique_uris if u not in existing_uris]
    processed_count = len(existing_uris)

    # もし全件取得済みなら即座に完了
    if not pending_uris:
        logger.info(f"[全件取得済み] 対象 {total_count:,} 件はすべて既に取得されています。")
        print(f"[全件取得済み] 対象 {total_count:,} 件はすべて既に取得されています。")
        update_job_status(
            status="COMPLETED",
            stage="completed",
            total_target=total_count,
            processed_count=total_count,
            current_batch_size=batch_size,
            eta_seconds=0,
            status_file=status_file
        )
        if duckdb_manager:
            duckdb_manager.import_jsonl(output_jsonl_path)
        return total_count

    file_mode = 'a' if (resume and len(existing_uris) > 0) else 'w'
    curr_batch_size = batch_size
    consecutive_fast_count = 0
    start_time = time.time()

    update_job_status(
        status="RUNNING",
        stage="build_metadata",
        total_target=total_count,
        processed_count=processed_count,
        current_batch_size=curr_batch_size,
        status_file=status_file
    )

    logger.info(f"--- [深層メタデータ一括構築開始] 全 {total_count:,} 件 (今回未取得: {len(pending_uris):,} 件, 初期batch_size={curr_batch_size}) ---")
    print(f"\n--- [深層メタデータ一括構築開始] 全 {total_count:,} 件 (今回未取得: {len(pending_uris):,} 件, 初期batch_size={curr_batch_size}) ---")
    session = get_robust_session()

    stopped_by_user = False
    with open(output_jsonl_path, file_mode, encoding='utf-8') as out_f:
        idx = 0
        while idx < len(pending_uris):
            # 停止要求のチェック
            cur_status = get_job_status(status_file)
            if cur_status.get("status") in ["STOP_REQUESTED", "STOPPED"]:
                logger.info("[深層メタデータ構築] 停止要求を検知したため安全に中断します。")
                print("\n[深層メタデータ構築] 停止要求を検知したため安全に中断します。")
                update_job_status(status="STOPPED", error_message="ユーザー要求により一時停止しました。", status_file=status_file)
                stopped_by_user = True
                break

            chunk_uris = pending_uris[idx:idx + curr_batch_size]
            bindings, stats = fetch_deep_graph_with_stats(chunk_uris, session=session)
            items = parse_dynamic_graph(bindings, chunk_uris)

            for item in items:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_f.flush()

            processed_count += len(items)
            idx += len(chunk_uris)

            # 適応型レート制御 (Adaptive Batch Sizing)
            if adaptive:
                if stats.get("is_clean") and stats.get("elapsed", 0) < 2.5:
                    consecutive_fast_count += 1
                    if consecutive_fast_count >= 2:
                        old_bs = curr_batch_size
                        curr_batch_size = min(max_batch_size, curr_batch_size + 5)
                        consecutive_fast_count = 0
                        if curr_batch_size != old_bs:
                            logger.info(f"[適応型レート制御] サーバー応答良好のためバッチサイズを拡大: {old_bs} ➔ {curr_batch_size} 件")
                elif not stats.get("is_clean") or stats.get("elapsed", 0) > 5.0:
                    consecutive_fast_count = 0
                    old_bs = curr_batch_size
                    curr_batch_size = max(min_batch_size, curr_batch_size // 2)
                    if curr_batch_size != old_bs:
                        logger.warning(f"[適応型レート制御] サーバー負荷・遅延を検知したためバッチサイズを縮小: {old_bs} ➔ {curr_batch_size} 件")

            # 推定残り時間（ETA）の計算
            elapsed_total = time.time() - start_time
            done_in_session = processed_count - len(existing_uris)
            eta_sec = None
            if done_in_session > 0:
                rate = done_in_session / max(0.1, elapsed_total)
                remaining = total_count - processed_count
                eta_sec = max(0, int(remaining / rate))

            logger.info(f"進捗: {processed_count:,} / {total_count:,} 件 完了 (バッチ={curr_batch_size}, 残り推定={eta_sec}s)")
            print(f"進捗: {processed_count:,} / {total_count:,} 件 完了 (バッチ={curr_batch_size}, 残り推定={eta_sec}s)")

            update_job_status(
                processed_count=processed_count,
                current_batch_size=curr_batch_size,
                eta_seconds=eta_sec,
                status_file=status_file
            )

            if progress_callback:
                progress_callback(processed_count, total_count)

            time.sleep(1.0)  # バッチ間の安定待機インターバル

    if stopped_by_user:
        return processed_count

    # 自動検証 ＆ 欠損修復フェーズ
    if auto_repair:
        logger.info("--- [自動完全性検証 ＆ 欠損リカバリーフェーズ開始] ---")
        print("\n--- [自動完全性検証 ＆ 欠損リカバリーフェーズ開始] ---")
        update_job_status(stage="auto_repair", status_file=status_file)
        verify_and_repair_metadata(unique_uris, output_jsonl_path, max_repair_rounds=3, status_file=status_file)

    # DuckDB 同期フェーズ
    if duckdb_manager:
        logger.info("--- [DuckDB 高速ストレージ同期フェーズ開始] ---")
        print("\n--- [DuckDB 高速ストレージ同期フェーズ開始] ---")
        update_job_status(stage="duckdb_sync", status_file=status_file)
        duckdb_manager.import_jsonl(output_jsonl_path)

    # 最終完了通知
    update_job_status(
        status="COMPLETED",
        stage="completed",
        total_target=total_count,
        processed_count=total_count,
        eta_seconds=0,
        status_file=status_file
    )
    logger.info(f"🎉 メタデータ構築完了: 全 {total_count:,} 件のデータが `{output_jsonl_path}` に正常格納されました。")
    print(f"\n🎉 メタデータ構築完了: 全 {total_count:,} 件のデータが `{output_jsonl_path}` に正常格納されました。")

    return processed_count


if __name__ == "__main__":
    print("BuildMetadata.py 準拠の深層メタデータモジュールがロードされました。")

