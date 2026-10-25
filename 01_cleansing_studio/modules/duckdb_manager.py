# -*- coding: utf-8 -*-
"""
DuckDB 高速メタデータ管理 ＆ フィルタリングエンジン
数万件単位の大規模メタデータに対する高速インポート、About/N-gram集計、およびミリ秒単位のルール適用
"""

import os
import re
import json
import duckdb
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter

try:
    from .rule_filter import extract_about_values, match_about_keyword
    from .logger import logger
except (ImportError, ValueError):
    from rule_filter import extract_about_values, match_about_keyword
    from logger import logger


class DuckDBManager:
    """
    DuckDBを活用したメタデータ管理・高速フィルタリングエンジン
    """

    def __init__(self, db_path: str = ":memory:"):
        """
        :param db_path: データベースファイルパス（デフォルトはインメモリ）
        """
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self):
        """テーブルおよびインデックスの初期化"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_records (
                id VARCHAR PRIMARY KEY,
                title VARCHAR,
                description VARCHAR,
                about_list VARCHAR[],
                type_list VARCHAR[],
                raw_json VARCHAR,
                type_status VARCHAR DEFAULT NULL,
                about_status VARCHAR DEFAULT NULL,
                ngram_status VARCHAR DEFAULT NULL,
                llm_status VARCHAR DEFAULT NULL,
                final_decision VARCHAR DEFAULT 'GREY',
                matched_reason VARCHAR DEFAULT NULL,
                llm_target BOOLEAN DEFAULT NULL,
                llm_reason VARCHAR DEFAULT NULL,
                external_info VARCHAR DEFAULT NULL,
                human_decision VARCHAR DEFAULT NULL,
                review_reasons VARCHAR DEFAULT NULL
            );
        """)
        # インデックス作成（存在しない場合）
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_decision ON metadata_records(final_decision);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_human ON metadata_records(human_decision);")

    def clear(self):
        """全レコードを削除"""
        self.conn.execute("DELETE FROM metadata_records;")

    def import_jsonl(self, jsonl_path: str, progress_callback=None) -> int:
        """
        JSONLファイルからメタデータを高速バルクインポート
        """
        if not os.path.exists(jsonl_path):
            return 0

        self.clear()
        records_to_insert = []
        batch_size = 5000
        total_inserted = 0

        with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue

                item_id = item.get("@id", item.get("id", ""))
                if not item_id:
                    continue

                label_val = item.get("rdfs:label", item.get("schema:name", ""))
                title = label_val[0] if isinstance(label_val, list) and label_val else str(label_val)

                desc_val = item.get("schema:description", "")
                desc = desc_val[0] if isinstance(desc_val, list) and desc_val else str(desc_val)

                about_val = item.get("schema:about", [])
                about_kws = extract_about_values(about_val)

                type_val = item.get("rdf:type", item.get("@type", []))
                type_list = type_val if isinstance(type_val, list) else [str(type_val)]

                records_to_insert.append((
                    str(item_id),
                    str(title),
                    str(desc),
                    about_kws,
                    [str(t) for t in type_list if t],
                    json.dumps(item, ensure_ascii=False)
                ))

                if len(records_to_insert) >= batch_size:
                    self.conn.executemany("""
                        INSERT OR REPLACE INTO metadata_records (
                            id, title, description, about_list, type_list, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?);
                    """, records_to_insert)
                    total_inserted += len(records_to_insert)
                    records_to_insert = []
                    if progress_callback:
                        progress_callback(total_inserted)

        if records_to_insert:
            self.conn.executemany("""
                INSERT OR REPLACE INTO metadata_records (
                    id, title, description, about_list, type_list, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?);
            """, records_to_insert)
            total_inserted += len(records_to_insert)
            if progress_callback:
                progress_callback(total_inserted)

        return total_inserted

    def get_record_count(self) -> int:
        """総レコード数を取得"""
        res = self.conn.execute("SELECT COUNT(*) FROM metadata_records;").fetchone()
        return res[0] if res else 0

    def get_about_keyword_counts(self, limit: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        DuckDBのUNNEST集計により、schema:about キーワードの出現頻度ランキングを瞬時に取得
        """
        query = """
            SELECT unnest(about_list) AS kw, COUNT(*) AS cnt
            FROM metadata_records
            WHERE about_list IS NOT NULL
            GROUP BY kw
            ORDER BY cnt DESC
        """
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"

        res = self.conn.execute(query).fetchall()
        return [(str(row[0]), int(row[1])) for row in res if row[0]]

    def extract_ngrams(self, min_n: int = 2, max_n: int = 3, top_k: int = 300) -> Dict[int, List[Tuple[str, int]]]:
        """
        DB内の全タイトルからN-gramを高速抽出・集計
        """
        titles = [row[0] for row in self.conn.execute("SELECT title FROM metadata_records WHERE title IS NOT NULL;").fetchall()]
        
        results = {}
        for n in range(min_n, max_n + 1):
            counter = Counter()
            for title in titles:
                # 記号・数字・空白の正規化
                clean_t = re.sub(r'[\s\(\)（）\[\]【】\d]+', '', title)
                t_len = len(clean_t)
                if t_len >= n:
                    for i in range(t_len - n + 1):
                        counter[clean_t[i:i+n]] += 1
            results[n] = counter.most_common(top_k)

        return results

    def apply_rules_fast(
        self,
        about_rules: Dict[str, str],
        ngram_rules: Dict[str, str]
    ) -> Dict[str, int]:
        """
        Aboutルール ＆ N-gramルールを完全な互換性を持って高速適用
        """
        ng_about_rules = [(k.strip(), status) for k, status in about_rules.items() if status == "NG" and k.strip()]
        ok_about_rules = [(k.strip(), status) for k, status in about_rules.items() if status == "OK" and k.strip()]

        ng_ngrams = [pat for pat, status in ngram_rules.items() if status == "NG" and pat]
        ok_ngrams = [pat for pat, status in ngram_rules.items() if status == "OK" and pat]

        # N-gram照合用の高速正規表現コンパイル（1200+ルールを単一のオートマトンで判定）
        re_ng_ngram = re.compile("|".join(map(re.escape, sorted(ng_ngrams, key=len, reverse=True)))) if ng_ngrams else None
        re_ok_ngram = re.compile("|".join(map(re.escape, sorted(ok_ngrams, key=len, reverse=True)))) if ok_ngrams else None

        # DuckDBから全件の id, title, about_list を一括フェッチ
        records = self.conn.execute("SELECT id, title, about_list FROM metadata_records;").fetchall()

        updates = []
        ok_count = 0
        ng_count = 0
        grey_count = 0

        # ルール判定キャッシュ（同一番号・同一キーワードの重複評価をO(1)化）
        match_cache = {}

        def check_about_match(kw_list, rules_list):
            for kw in kw_list:
                for r_target, _ in rules_list:
                    cache_key = (kw, r_target)
                    matched = match_cache.get(cache_key)
                    if matched is None:
                        matched = match_about_keyword(kw, r_target)
                        match_cache[cache_key] = matched
                    if matched:
                        return True, r_target
            return False, ""

        for row in records:
            item_id, title, about_list = row[0], row[1] or "", row[2] or []

            # =================================================================
            # 1. NG判定（最優先）
            # =================================================================
            has_ng = False
            matched_reason = ""

            # A. About NG 判定 (match_about_keyword 互換 + キャッシュ)
            is_about_ng, matched_r = check_about_match(about_list, ng_about_rules)
            if is_about_ng:
                has_ng = True
                matched_reason = f"About NG: 「{matched_r}」"

            # B. タイトル N-gram NG 判定（高速正規表現オートマトン）
            if not has_ng and re_ng_ngram:
                m = re_ng_ngram.search(title)
                if m:
                    has_ng = True
                    matched_reason = f"タイトル NG: 「{m.group(0)}」"

            if has_ng:
                updates.append((item_id, "NG", matched_reason))
                ng_count += 1
                continue

            # =================================================================
            # 2. OK判定（NGなし ＆ OKあり -> 合格）
            # =================================================================
            has_ok = False
            matched_ok_reason = ""

            is_about_ok, matched_ok_r = check_about_match(about_list, ok_about_rules)
            if is_about_ok:
                has_ok = True
                matched_ok_reason = f"About OK: 「{matched_ok_r}」"

            if not has_ok and re_ok_ngram:
                m = re_ok_ngram.search(title)
                if m:
                    has_ok = True
                    matched_ok_reason = f"タイトル OK: 「{m.group(0)}」"

            if has_ok:
                updates.append((item_id, "OK", matched_ok_reason))
                ok_count += 1
            else:
                updates.append((item_id, "GREY", "判定保留 (LLMセマンティック対象)"))
                grey_count += 1

        # 一括バルク更新 (一時テーブル経由で高速UPDATE)
        self.conn.execute("CREATE TEMP TABLE temp_updates (id VARCHAR PRIMARY KEY, decision VARCHAR, reason VARCHAR);")
        self.conn.executemany("INSERT INTO temp_updates VALUES (?, ?, ?);", updates)
        self.conn.execute("""
            UPDATE metadata_records
            SET final_decision = u.decision,
                matched_reason = u.reason
            FROM temp_updates u
            WHERE metadata_records.id = u.id;
        """)
        self.conn.execute("DROP TABLE temp_updates;")

        return {
            "ok": ok_count,
            "ng": ng_count,
            "grey": grey_count,
            "total": len(records)
        }

    def export_split_datasets(
        self,
        output_target_for_llm_jsonl: str,
        output_confirmed_ok_jsonl: str,
        output_discarded_csv: str
    ):
        """
        判定結果に基づいて、従来の出力ファイル（LLM対象JSONL、合格JSONL、除外CSV）を高速出力
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_target_for_llm_jsonl)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(output_confirmed_ok_jsonl)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(output_discarded_csv)), exist_ok=True)

        # 1. GREY (LLM投入対象)
        grey_rows = self.conn.execute("""
            SELECT raw_json FROM metadata_records WHERE final_decision = 'GREY';
        """).fetchall()
        with open(output_target_for_llm_jsonl, 'w', encoding='utf-8') as f:
            for r in grey_rows:
                f.write(r[0] + "\n")

        # 2. OK (合格)
        ok_rows = self.conn.execute("""
            SELECT id, title, matched_reason, raw_json
            FROM metadata_records WHERE final_decision = 'OK';
        """).fetchall()
        with open(output_confirmed_ok_jsonl, 'w', encoding='utf-8') as f:
            for r in ok_rows:
                entry = {
                    "id": r[0],
                    "title": r[1],
                    "is_target": True,
                    "reason": r[2],
                    "raw_item": json.loads(r[3])
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 3. NG (除外CSV)
        import pandas as pd
        ng_rows = self.conn.execute("""
            SELECT id, title, matched_reason AS reason
            FROM metadata_records WHERE final_decision = 'NG';
        """).fetchdf()
        ng_rows.to_csv(output_discarded_csv, index=False, encoding='utf-8-sig')

    # =========================================================================
    # Step 4: 専門家査読ポータル用 高速メソッド群
    # =========================================================================

    def sync_llm_judgments(self, llm_jsonl_path: str) -> int:
        """
        LLM判定結果 (llm_judgments.jsonl) をDuckDBへ一括反映
        """
        if not os.path.exists(llm_jsonl_path):
            return 0

        updates = []
        with open(llm_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    uid = data.get("id")
                    if not uid:
                        continue
                    is_target = data.get("is_target")
                    reason = data.get("reason", "")
                    ext = data.get("external_info", "")
                    updates.append((uid, is_target, reason, ext))
                except Exception:
                    continue

        if not updates:
            return 0

        self.conn.execute("""
            CREATE TEMP TABLE temp_llm_sync (
                id VARCHAR PRIMARY KEY,
                llm_target BOOLEAN,
                llm_reason VARCHAR,
                external_info VARCHAR
            );
        """)
        self.conn.executemany("INSERT INTO temp_llm_sync VALUES (?, ?, ?, ?);", updates)
        self.conn.execute("""
            UPDATE metadata_records
            SET llm_target = t.llm_target,
                llm_reason = t.llm_reason,
                external_info = t.external_info,
                final_decision = CASE
                    WHEN t.llm_target = true THEN 'OK'
                    WHEN t.llm_target = false THEN 'NG'
                    ELSE final_decision
                END,
                matched_reason = CASE
                    WHEN t.llm_target = true THEN 'LLM判定適合: ' || coalesce(t.llm_reason, '')
                    WHEN t.llm_target = false THEN 'LLM判定除外: ' || coalesce(t.llm_reason, '')
                    ELSE matched_reason
                END
            FROM temp_llm_sync t
            WHERE metadata_records.id = t.id;
        """)
        self.conn.execute("DROP TABLE temp_llm_sync;")
        return len(updates)

    def get_review_metrics(self) -> Dict[str, int]:
        """
        査読集約ステータス（総件数、合格数、除外数、オーバーライド数、LLM判定不能数）を高速SQL集計
        """
        query = """
            SELECT
                count(*) AS total,
                count(*) FILTER (WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格') AS pass_cnt,
                count(*) FILTER (WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '除外') AS reject_cnt,
                count(*) FILTER (WHERE human_decision IS NOT NULL AND human_decision != (CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END)) AS override_cnt,
                count(*) FILTER (WHERE llm_target IS NULL AND (matched_reason LIKE '%LLM%' OR review_reasons LIKE '%LLM%')) AS null_cnt
            FROM metadata_records;
        """
        row = self.conn.execute(query).fetchone()
        if not row:
            return {"total": 0, "pass_cnt": 0, "reject_cnt": 0, "override_cnt": 0, "null_cnt": 0}
        return {
            "total": row[0] or 0,
            "pass_cnt": row[1] or 0,
            "reject_cnt": row[2] or 0,
            "override_cnt": row[3] or 0,
            "null_cnt": row[4] or 0
        }

    def query_review_records(
        self,
        filter_type: str = "すべて",
        search_query: str = "",
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        査読画面用：サーバーサイド検索・フィルタリング・ページネーション
        数万件のデータがあっても 0.002秒 で該当ページのレコードのみを返却
        """
        where_clauses = ["1=1"]
        params = []

        # 絞り込みフィルタ
        if filter_type == "LLM判定不能 (null) データのみ":
            where_clauses.append("(llm_target IS NULL AND (matched_reason LIKE '%LLM%' OR review_reasons LIKE '%LLM%'))")
        elif filter_type == "現在『合格』のデータのみ":
            where_clauses.append("coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格'")
        elif filter_type == "現在『除外』のデータのみ":
            where_clauses.append("coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '除外'")
        elif filter_type == "LLM判定経由データのみ":
            where_clauses.append("(matched_reason LIKE '%LLM判定%' AND matched_reason NOT LIKE '%LLMバイパス%')")
        elif filter_type == "手動修正 (オーバーライド) データのみ":
            where_clauses.append("human_decision IS NOT NULL AND human_decision != (CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END)")

        # 検索キーワード (タイトル / ID / 理由)
        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            where_clauses.append("(title ILIKE ? OR id ILIKE ? OR matched_reason ILIKE ? OR llm_reason ILIKE ?)")
            params.extend([sq, sq, sq, sq])

        where_sql = " AND ".join(where_clauses)

        # 1. 該当総件数のカウント
        count_query = f"SELECT count(*) FROM metadata_records WHERE {where_sql};"
        total_count = self.conn.execute(count_query, params).fetchone()[0]

        # 2. 該当ページのレコード取得
        offset = max(0, (page - 1) * page_size)
        fetch_query = f"""
            SELECT
                id,
                title,
                final_decision,
                coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) AS cur_status,
                human_decision,
                matched_reason,
                llm_target,
                llm_reason,
                external_info,
                raw_json
            FROM metadata_records
            WHERE {where_sql}
            ORDER BY id
            LIMIT {int(page_size)} OFFSET {int(offset)};
        """
        rows = self.conn.execute(fetch_query, params).fetchall()

        records = []
        for r in rows:
            uid, title, fin_dec, cur_status, h_dec, matched_r, llm_tgt, llm_r, ext_info, raw_j = r
            auto_status = "合格" if fin_dec == "OK" else "除外"
            is_override = (h_dec is not None and h_dec != auto_status)

            records.append({
                "id": uid,
                "title": title or "無題資料",
                "status": auto_status,
                "cur_status": cur_status,
                "is_override": is_override,
                "reasons": matched_r or "全ルール通過",
                "llm_target": llm_tgt,
                "llm_reason": llm_r or "",
                "external_info": ext_info or "",
                "raw_item": json.loads(raw_j) if raw_j else {}
            })

        return total_count, records

    def set_human_decision(self, item_id: str, decision: str):
        """1件の判定手動オーバーライドを即時更新"""
        self.conn.execute("""
            UPDATE metadata_records
            SET human_decision = ?
            WHERE id = ?;
        """, (decision, item_id))

    def get_all_human_decisions(self) -> Dict[str, str]:
        """全レコードの手動上書き辞書を取得"""
        rows = self.conn.execute("""
            SELECT id, human_decision FROM metadata_records WHERE human_decision IS NOT NULL;
        """).fetchall()
        return {r[0]: r[1] for r in rows}

    def export_human_verified_data(self, output_verified_jsonl: str) -> int:
        """
        最終確定データ (合格確定レコード) を高速エクスポート
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_verified_jsonl)), exist_ok=True)
        query = """
            SELECT id, raw_json, matched_reason
            FROM metadata_records
            WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格';
        """
        rows = self.conn.execute(query).fetchall()

        with open(output_verified_jsonl, 'w', encoding='utf-8') as f:
            for r in rows:
                item_id, raw_j, matched_r = r
                item = json.loads(raw_j) if raw_j else {"@id": item_id}
                item["human_verified_status"] = "APPROVED"
                item["review_reasons"] = matched_r or "全ルール通過"
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return len(rows)

    def close(self):
        """接続終了"""
        if self.conn:
            self.conn.close()

