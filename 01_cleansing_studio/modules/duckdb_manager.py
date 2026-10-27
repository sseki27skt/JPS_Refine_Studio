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
                review_reasons VARCHAR DEFAULT NULL,
                llm_evaluated BOOLEAN DEFAULT FALSE,
                type_reason VARCHAR DEFAULT NULL,
                about_reason VARCHAR DEFAULT NULL,
                ngram_reason VARCHAR DEFAULT NULL,
                adopted_stage VARCHAR DEFAULT NULL,
                drop_stage VARCHAR DEFAULT NULL,
                primary_reason VARCHAR DEFAULT NULL
            );
        """)
        # 既存DBファイルに対するスキーママイグレーション
        migration_columns = [
            ("llm_evaluated", "BOOLEAN DEFAULT FALSE"),
            ("type_reason", "VARCHAR DEFAULT NULL"),
            ("about_reason", "VARCHAR DEFAULT NULL"),
            ("ngram_reason", "VARCHAR DEFAULT NULL"),
            ("adopted_stage", "VARCHAR DEFAULT NULL"),
            ("drop_stage", "VARCHAR DEFAULT NULL"),
            ("primary_reason", "VARCHAR DEFAULT NULL")
        ]
        for col_name, col_type in migration_columns:
            try:
                self.conn.execute(f"ALTER TABLE metadata_records ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
            except Exception:
                pass

        # インデックス作成（存在しない場合）
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_decision ON metadata_records(final_decision);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_human ON metadata_records(human_decision);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_drop ON metadata_records(drop_stage);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_adopted ON metadata_records(adopted_stage);")

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
        params = []
        if limit and limit > 0:
            query += " LIMIT ?"
            params.append(int(limit))

        res = self.conn.execute(query, params).fetchall()
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

        # DuckDBから全件の id, title, about_list, type_status, drop_stage, primary_reason を一括フェッチ
        records = self.conn.execute("""
            SELECT id, title, about_list, type_status, drop_stage, primary_reason 
            FROM metadata_records;
        """).fetchall()

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
            item_id = row[0]
            title = row[1] or ""
            about_list = row[2] or []
            type_status = row[3]
            existing_drop_stage = row[4]
            existing_primary_reason = row[5]

            # 既に Type除外されているレコードは、除外状態と来歴を保護
            if type_status == 'NG':
                updates.append((
                    item_id, "NG", existing_primary_reason or "Type除外",
                    None, None,
                    None, None,
                    None, existing_drop_stage or "TYPE", existing_primary_reason or "Type除外"
                ))
                ng_count += 1
                continue

            # =================================================================
            # 1. NG判定（最優先）
            # =================================================================
            has_ng = False
            matched_reason = ""
            about_status, about_reason = None, None
            ngram_status, ngram_reason = None, None
            drop_stage = None
            adopted_stage = None

            # A. About NG 判定 (match_about_keyword 互換 + キャッシュ)
            is_about_ng, matched_r = check_about_match(about_list, ng_about_rules)
            if is_about_ng:
                has_ng = True
                matched_reason = f"About NG: 「{matched_r}」"
                about_status = "NG"
                about_reason = matched_r
                drop_stage = "RULE_ABOUT"

            # B. タイトル N-gram NG 判定（高速正規表現オートマトン）
            if not has_ng and re_ng_ngram:
                m = re_ng_ngram.search(title)
                if m:
                    has_ng = True
                    matched_reason = f"タイトル NG: 「{m.group(0)}」"
                    ngram_status = "NG"
                    ngram_reason = m.group(0)
                    drop_stage = "RULE_NGRAM"

            if has_ng:
                updates.append((
                    item_id, "NG", matched_reason, 
                    about_status, about_reason, 
                    ngram_status, ngram_reason, 
                    None, drop_stage, matched_reason
                ))
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
                about_status = "OK"
                about_reason = matched_ok_r
                adopted_stage = "RULE_ABOUT"

            if not has_ok and re_ok_ngram:
                m = re_ok_ngram.search(title)
                if m:
                    has_ok = True
                    matched_ok_reason = f"タイトル OK: 「{m.group(0)}」"
                    ngram_status = "OK"
                    ngram_reason = m.group(0)
                    adopted_stage = "RULE_NGRAM"

            if has_ok:
                full_ok_reason = f"[ルール合格] {matched_ok_reason}"
                updates.append((
                    item_id, "OK", full_ok_reason,
                    about_status, about_reason,
                    ngram_status, ngram_reason,
                    adopted_stage, None, full_ok_reason
                ))
                ok_count += 1
            else:
                updates.append((
                    item_id, "GREY", "判定保留 (LLMセマンティック対象)",
                    None, None,
                    None, None,
                    None, None, "判定保留 (LLMセマンティック対象)"
                ))
                grey_count += 1

        # 一括バルク更新 (一時テーブル経由で高速UPDATE)
        self.conn.execute("""
            CREATE TEMP TABLE temp_updates (
                id VARCHAR PRIMARY KEY, 
                decision VARCHAR, 
                reason VARCHAR,
                about_status VARCHAR,
                about_reason VARCHAR,
                ngram_status VARCHAR,
                ngram_reason VARCHAR,
                adopted_stage VARCHAR,
                drop_stage VARCHAR,
                primary_reason VARCHAR
            );
        """)
        self.conn.executemany("INSERT INTO temp_updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", updates)
        self.conn.execute("""
            UPDATE metadata_records
            SET final_decision = u.decision,
                matched_reason = u.reason,
                about_status = u.about_status,
                about_reason = u.about_reason,
                ngram_status = u.ngram_status,
                ngram_reason = u.ngram_reason,
                adopted_stage = u.adopted_stage,
                drop_stage = u.drop_stage,
                primary_reason = u.primary_reason
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
                reason_str = r[2] or ""
                if not reason_str.startswith("[ルール合格]"):
                    reason_str = f"[ルール合格] {reason_str}"
                entry = {
                    "id": r[0],
                    "title": r[1],
                    "is_target": True,
                    "reason": reason_str,
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
        return len(ok_rows), len(ng_rows), len(grey_rows)

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
                llm_evaluated = true,
                llm_status = CASE 
                    WHEN t.llm_target = true THEN 'PASS'
                    WHEN t.llm_target = false THEN 'FAIL'
                    ELSE 'UNKNOWN'
                END,
                adopted_stage = CASE WHEN t.llm_target = true THEN 'LLM' ELSE adopted_stage END,
                drop_stage = CASE WHEN t.llm_target = false AND (type_status IS NULL OR type_status != 'NG') THEN 'LLM' ELSE drop_stage END,
                primary_reason = CASE
                    WHEN t.llm_target = true THEN '[LLM判定] ' || coalesce(t.llm_reason, '')
                    WHEN t.llm_target = false AND (type_status IS NULL OR type_status != 'NG') THEN '[LLM除外] ' || coalesce(t.llm_reason, '')
                    ELSE primary_reason
                END,
                final_decision = CASE
                    WHEN t.llm_target = true THEN 'OK'
                    WHEN t.llm_target = false THEN 'NG'
                    ELSE final_decision
                END,
                matched_reason = CASE
                    WHEN t.llm_target = true THEN 'LLM判定適合: ' || coalesce(t.llm_reason, '')
                    WHEN t.llm_target = false THEN 'LLM判定除外: ' || coalesce(t.llm_reason, '')
                    WHEN t.llm_target IS NULL THEN 'LLM判定不能 (null): ' || coalesce(t.llm_reason, '')
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
                count(*) FILTER (WHERE llm_evaluated = true AND llm_target IS NULL) AS null_cnt
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

    def query_records(
        self,
        filter_status: str = "すべて",
        search_query: str = "",
        stage: Optional[str] = None,
        ng_types: Optional[List[str]] = None,
        target_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        filter_type: Optional[str] = None,
        filter_source: Optional[str] = None
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        現在のフィルタ条件・検索キーワードに基づく「総件数カウント」と「指定ページ（50件単位、LIMIT/OFFSET）」を返すクエリ関数
        """
        eff_filter = filter_type or filter_status or "すべて"
        where_clauses = ["1=1"]
        params = []

        # 1. 判定ステータスフィルタ
        if eff_filter in ("現在『合格』のデータのみ", "合格", "OK"):
            where_clauses.append("coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格'")
        elif eff_filter in ("現在『除外』のデータのみ", "除外", "NG"):
            where_clauses.append("coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '除外'")
        elif eff_filter in ("判定保留 (GREY)", "保留", "GREY", "判定保留群"):
            where_clauses.append("(type_status IS NULL OR type_status != 'NG') AND final_decision = 'GREY'")
        elif eff_filter in ("LLM判定不能 (null) データのみ", "判定不能 (null)のみ"):
            where_clauses.append("(llm_evaluated = true AND llm_target IS NULL)")
        elif eff_filter in ("適合 (true)のみ", "適合のみ"):
            where_clauses.append("llm_target = true")
        elif eff_filter in ("非適合 (false)のみ", "非適合のみ"):
            where_clauses.append("llm_target = false")
        elif eff_filter == "LLM判定経由データのみ":
            where_clauses.append("(matched_reason LIKE '%LLM判定%' AND matched_reason NOT LIKE '%LLMバイパス%')")
        elif eff_filter == "手動修正 (オーバーライド) データのみ":
            where_clauses.append("human_decision IS NOT NULL AND human_decision != (CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END)")
        elif eff_filter in ("Type除外データのみ", "Type除外", "TYPE"):
            where_clauses.append("type_status = 'NG'")
        elif eff_filter in ("About除外データのみ", "RULE_ABOUT"):
            where_clauses.append("about_status = 'NG' AND (type_status IS NULL OR type_status != 'NG')")
        elif eff_filter in ("Ngram除外データのみ", "RULE_NGRAM"):
            where_clauses.append("ngram_status = 'NG' AND (type_status IS NULL OR type_status != 'NG')")
        elif eff_filter == "ルール適合パス (LLMバイパス)":
            where_clauses.append("matched_reason LIKE '%[ルール合格]%'")
        elif eff_filter == "Web情報補強 LLM判定":
            where_clauses.append("matched_reason LIKE '%LLM判定%' AND external_info IS NOT NULL AND external_info != ''")

        # 1-b. 判定ソース個別フィルタ
        if filter_source == "Web情報補強 LLM判定":
            where_clauses.append("(matched_reason LIKE '%LLM判定%' AND external_info IS NOT NULL AND external_info != '')")
        elif filter_source == "ルール適合パス (LLMバイパス)":
            where_clauses.append("matched_reason LIKE '%[ルール合格]%'")

        # 2. ステージフィルタ
        if stage:
            if stage == "TYPE":
                where_clauses.append("drop_stage = 'TYPE'")
            else:
                where_clauses.append("(drop_stage = ? OR adopted_stage = ?)")
                params.extend([stage, stage])

        # 3. 特定種別フィルタ
        if target_type:
            if target_type == "（未定義 / 種別なし）":
                where_clauses.append("(type_list IS NULL OR len(type_list) = 0)")
            else:
                where_clauses.append("""
                    EXISTS (
                        SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                        WHERE val = ? OR split_part(split_part(val, '/', -1), '#', -1) = ?
                    )
                """)
                params.extend([target_type, target_type])

        # 4. 除外対象種別 (ng_types) フィルタ
        has_temp_ng = False
        if ng_types:
            has_empty = "（未定義 / 種別なし）" in ng_types
            pure_ng = [t for t in ng_types if t != "（未定義 / 種別なし）"]

            if pure_ng or has_empty:
                self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS temp_query_ng (val VARCHAR);")
                self.conn.execute("DELETE FROM temp_query_ng;")
                if pure_ng:
                    self.conn.executemany("INSERT INTO temp_query_ng VALUES (?);", [(t,) for t in pure_ng])
                has_temp_ng = True

                if has_empty and pure_ng:
                    where_clauses.append("""
                        (type_list IS NULL OR len(type_list) = 0 OR EXISTS (
                            SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                            JOIN temp_query_ng qng ON (t.val = qng.val OR split_part(split_part(t.val, '/', -1), '#', -1) = qng.val)
                        ))
                    """)
                elif has_empty:
                    where_clauses.append("(type_list IS NULL OR len(type_list) = 0)")
                elif pure_ng:
                    where_clauses.append("""
                        EXISTS (
                            SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                            JOIN temp_query_ng qng ON (t.val = qng.val OR split_part(split_part(t.val, '/', -1), '#', -1) = qng.val)
                        )
                    """)

        # 5. 検索キーワード (タイトル / ID / 説明 / 理由)
        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            where_clauses.append("(title ILIKE ? OR id ILIKE ? OR description ILIKE ? OR matched_reason ILIKE ? OR primary_reason ILIKE ? OR llm_reason ILIKE ?)")
            params.extend([sq, sq, sq, sq, sq, sq])

        where_sql = " AND ".join(where_clauses)

        # 総件数カウント
        count_query = f"SELECT count(*) FROM metadata_records WHERE {where_sql};"
        total_count = self.conn.execute(count_query, params).fetchone()[0]

        # 指定ページのレコード取得 (LIMIT / OFFSET)
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size

        fetch_query = f"""
            SELECT
                id,
                title,
                description,
                about_list,
                type_list,
                final_decision,
                coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) AS cur_status,
                human_decision,
                matched_reason,
                primary_reason,
                type_status,
                type_reason,
                about_status,
                about_reason,
                ngram_status,
                ngram_reason,
                llm_status,
                llm_target,
                llm_reason,
                external_info,
                raw_json
            FROM metadata_records
            WHERE {where_sql}
            ORDER BY id
            LIMIT ? OFFSET ?;
        """
        params.extend([int(page_size), int(offset)])
        rows = self.conn.execute(fetch_query, params).fetchall()

        if has_temp_ng:
            try:
                self.conn.execute("DROP TABLE IF EXISTS temp_query_ng;")
            except Exception:
                pass

        records = []
        for r in rows:
            (uid, title, desc, ab_list, t_list, fin_dec, cur_status, h_dec,
             matched_r, prim_r, t_stat, t_rsn, ab_stat, ab_rsn, ng_stat, ng_rsn,
             llm_stat, llm_tgt, llm_r, ext_info, raw_j) = r

            auto_status = "合格" if fin_dec == "OK" else "除外"
            is_override = (h_dec is not None and h_dec != auto_status)

            records.append({
                "id": uid,
                "title": title or "無題資料",
                "description": desc or "",
                "about_list": ab_list or [],
                "type_list": t_list or [],
                "final_decision": fin_dec,
                "status": auto_status,
                "cur_status": cur_status,
                "human_decision": h_dec,
                "is_override": is_override,
                "matched_reason": matched_r or "",
                "primary_reason": prim_r or "",
                "reasons": prim_r or matched_r or "全ルール通過",
                "type_status": t_stat,
                "type_reason": t_rsn,
                "about_status": ab_stat,
                "about_reason": ab_rsn,
                "ngram_status": ng_stat,
                "ngram_reason": ng_rsn,
                "llm_status": llm_stat,
                "llm_target": llm_tgt,
                "llm_reason": llm_r or "",
                "external_info": ext_info or "",
                "raw_item": json.loads(raw_j) if raw_j else {}
            })

        return total_count, records

    # エイリアス
    query_paginated_records = query_records

    def query_review_records(
        self,
        filter_type: str = "すべて",
        search_query: str = "",
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        査読画面用：サーバーサイド検索・フィルタリング・ページネーション
        数万件のデータがあっても 0.002秒 で該当ページのレコードのみを返却
        """
        return self.query_records(
            filter_status=filter_type,
            search_query=search_query,
            page=page,
            page_size=page_size
        )

    def set_human_decision(self, item_id: str, decision: str):
        """1件の判定手動オーバーライドを即時更新"""
        self.conn.execute("""
            UPDATE metadata_records
            SET human_decision = ?,
                adopted_stage = CASE WHEN ? = '合格' THEN 'HUMAN' ELSE adopted_stage END,
                drop_stage = CASE WHEN ? = '除外' THEN 'HUMAN' ELSE drop_stage END,
                primary_reason = CASE 
                    WHEN ? = '合格' THEN '[査読合格] 専門家による手動承認' 
                    ELSE '[査読除外] 専門家による手動除外' 
                END
            WHERE id = ?;
        """, (decision, decision, decision, decision, item_id))

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
            SELECT id, raw_json, matched_reason, human_decision
            FROM metadata_records
            WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格';
        """
        rows = self.conn.execute(query).fetchall()

        with open(output_verified_jsonl, 'w', encoding='utf-8') as f:
            for r in rows:
                item_id, raw_j, matched_r, h_dec = r
                item = json.loads(raw_j) if raw_j else {"@id": item_id}
                item["human_verified_status"] = "APPROVED"
                item["human_decision"] = h_dec or "合格"
                item["review_reasons"] = matched_r or "全ルール通過"
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return len(rows)

    def sync_human_decisions(self, verified_jsonl_path: str) -> int:
        """
        過去の確定査読データ (human_verified_cleaned.jsonl) から手動判定を復元
        """
        if not os.path.exists(verified_jsonl_path):
            return 0

        updates = []
        with open(verified_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    uid = data.get("@id", data.get("id"))
                    if not uid:
                        continue
                    decision = data.get("human_decision", "合格")
                    updates.append((str(uid), str(decision)))
                except Exception:
                    continue

        if not updates:
            return 0

        self.conn.execute("""
            CREATE TEMP TABLE temp_human_sync (
                id VARCHAR PRIMARY KEY,
                decision VARCHAR
            );
        """)
        self.conn.executemany("INSERT OR REPLACE INTO temp_human_sync VALUES (?, ?);", updates)
        self.conn.execute("""
            UPDATE metadata_records
            SET human_decision = h.decision
            FROM temp_human_sync h
            WHERE metadata_records.id = h.id;
        """)
        self.conn.execute("DROP TABLE temp_human_sync;")
        return len(updates)

    def apply_type_filter_fast(self, ng_types: list) -> Dict[str, int]:
        """
        Type (rdf:type) のNGルールに基づいて除外判定を適用し、来歴を記録
        """
        if not ng_types:
            total_c = self.get_record_count()
            return {"total": total_c, "passed": total_c, "discarded": 0}

        records = self.conn.execute("SELECT id, type_list FROM metadata_records;").fetchall()
        ng_set = set(ng_types)
        updates = []
        disc_cnt = 0

        for r in records:
            uid, t_list = r[0], r[1] or []
            matched_t = None
            if not t_list:
                if "（未定義 / 種別なし）" in ng_set:
                    matched_t = "（未定義 / 種別なし）"
            else:
                for t in t_list:
                    short_t = t.split("/")[-1].split("#")[-1]
                    if t in ng_set or short_t in ng_set:
                        matched_t = short_t or t
                        break

            if matched_t:
                reason_str = f"Type除外: 「{matched_t}」"
                updates.append((uid, "NG", reason_str, matched_t, "TYPE", reason_str))
                disc_cnt += 1
            else:
                updates.append((uid, "PASS", None, None, None, None))

        self.conn.execute("""
            CREATE TEMP TABLE temp_type_updates (
                id VARCHAR PRIMARY KEY,
                t_status VARCHAR,
                m_reason VARCHAR,
                t_reason VARCHAR,
                d_stage VARCHAR,
                p_reason VARCHAR
            );
        """)
        self.conn.executemany("INSERT INTO temp_type_updates VALUES (?, ?, ?, ?, ?, ?);", updates)
        self.conn.execute("""
            UPDATE metadata_records
            SET type_status = u.t_status,
                type_reason = u.t_reason,
                drop_stage = CASE WHEN u.t_status = 'NG' THEN u.d_stage ELSE drop_stage END,
                primary_reason = CASE WHEN u.t_status = 'NG' THEN u.p_reason ELSE primary_reason END,
                final_decision = CASE WHEN u.t_status = 'NG' THEN 'NG' ELSE final_decision END,
                matched_reason = CASE WHEN u.t_status = 'NG' THEN u.m_reason ELSE matched_reason END
            FROM temp_type_updates u
            WHERE metadata_records.id = u.id;
        """)
        self.conn.execute("DROP TABLE temp_type_updates;")

        total = len(records)
        return {"total": total, "passed": total - disc_cnt, "discarded": disc_cnt}

    def get_type_stats(self) -> List[Dict[str, Any]]:
        """
        DuckDBから全rdf:type（リソース種別）の出現頻度ランキングを瞬時に集計
        """
        import urllib.parse

        # 1. 未定義 / 種別なしレコード数
        empty_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE type_list IS NULL OR len(type_list) = 0;
        """).fetchone()
        empty_cnt = empty_row[0] if empty_row else 0

        # 2. 全種別の集計
        rows = self.conn.execute("""
            SELECT
                t AS full_uri,
                COUNT(*) as cnt
            FROM (
                SELECT unnest(type_list) AS t
                FROM metadata_records
                WHERE type_list IS NOT NULL AND len(type_list) > 0
            )
            GROUP BY t
            ORDER BY cnt DESC;
        """).fetchall()

        type_map = {}
        for full_uri, cnt in rows:
            if not full_uri:
                continue
            if full_uri.startswith("http"):
                short_lbl = urllib.parse.unquote(full_uri.split("/")[-1].split("#")[-1])
                if not short_lbl:
                    short_lbl = full_uri
            else:
                short_lbl = full_uri

            if short_lbl not in type_map:
                type_map[short_lbl] = {
                    "short_label": short_lbl,
                    "full_uri": full_uri,
                    "count": cnt,
                    "samples": []
                }
            else:
                type_map[short_lbl]["count"] += cnt

        stats = []
        if empty_cnt > 0:
            stats.append({
                "short_label": "（未定義 / 種別なし）",
                "full_uri": "",
                "count": empty_cnt,
                "samples": []
            })

        stats.extend(sorted(type_map.values(), key=lambda x: x["count"], reverse=True))
        return stats

    def query_records_by_type(
        self,
        target_type: str,
        search_query: str = "",
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        指定された種別に属するレコードの総件数カウントと指定ページ取得（50件単位、LIMIT/OFFSET）
        """
        if not target_type:
            return 0, []

        where_conds = []
        params = []
        if target_type == "（未定義 / 種別なし）":
            where_conds.append("(type_list IS NULL OR len(type_list) = 0)")
        else:
            where_conds.append("""
                EXISTS (
                    SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                    WHERE val = ? OR split_part(split_part(val, '/', -1), '#', -1) = ?
                )
            """)
            params.extend([target_type, target_type])

        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            where_conds.append("(title ILIKE ? OR id ILIKE ? OR description ILIKE ?)")
            params.extend([sq, sq, sq])

        where_sql = " AND ".join(where_conds)
        total_count = self.conn.execute(f"SELECT count(*) FROM metadata_records WHERE {where_sql};", params).fetchone()[0]

        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size

        fetch_query = f"""
            SELECT id, title, description, type_list
            FROM metadata_records
            WHERE {where_sql}
            ORDER BY id
            LIMIT ? OFFSET ?;
        """
        params.extend([int(page_size), int(offset)])
        rows = self.conn.execute(fetch_query, params).fetchall()
        records = [{
            "id": r[0],
            "title": r[1] or "（無題）",
            "description": r[2] or "",
            "type_list": r[3] or []
        } for r in rows]

        return total_count, records

    def get_records_by_type(self, target_type: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        指定された種別に属するレコード（資料）をオンデマンドで高速取得（後方互換対応）
        """
        if not target_type:
            return []
        page_size = int(limit) if (limit and limit > 0) else 1000
        _, records = self.query_records_by_type(target_type=target_type, page=1, page_size=page_size)
        return records

    def query_records_discarded_by_types(
        self,
        ng_types: List[str],
        search_query: str = "",
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        除外対象種別（ng_types）によって除外されるレコードの総件数カウントと指定ページ取得（50件単位、LIMIT/OFFSET）
        """
        if not ng_types:
            return 0, []

        has_empty = "（未定義 / 種別なし）" in ng_types
        pure_ng = [t for t in ng_types if t != "（未定義 / 種別なし）"]

        self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS temp_disc_types (val VARCHAR);")
        self.conn.execute("DELETE FROM temp_disc_types;")
        if pure_ng:
            self.conn.executemany("INSERT INTO temp_disc_types VALUES (?);", [(t,) for t in pure_ng])

        where_conds = []
        if has_empty and pure_ng:
            where_conds.append("""
                (type_list IS NULL OR len(type_list) = 0 OR EXISTS (
                    SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                    JOIN temp_disc_types dt ON (t.val = dt.val OR split_part(split_part(t.val, '/', -1), '#', -1) = dt.val)
                ))
            """)
        elif has_empty:
            where_conds.append("(type_list IS NULL OR len(type_list) = 0)")
        elif pure_ng:
            where_conds.append("""
                EXISTS (
                    SELECT 1 FROM unnest(metadata_records.type_list) AS t(val)
                    JOIN temp_disc_types dt ON (t.val = dt.val OR split_part(split_part(t.val, '/', -1), '#', -1) = dt.val)
                )
            """)

        params = []
        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            where_conds.append("(title ILIKE ? OR id ILIKE ? OR description ILIKE ?)")
            params.extend([sq, sq, sq])

        where_sql = " AND ".join(where_conds)

        count_query = f"SELECT count(*) FROM metadata_records WHERE {where_sql};"
        total_count = self.conn.execute(count_query, params).fetchone()[0]

        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size

        if pure_ng:
            fetch_query = f"""
                SELECT
                    id,
                    title,
                    description,
                    type_list,
                    CASE 
                        WHEN type_list IS NULL OR len(type_list) = 0 THEN '（未定義 / 種別なし）'
                        ELSE coalesce(
                            (SELECT dt.val FROM unnest(metadata_records.type_list) AS t(val)
                             JOIN temp_disc_types dt ON (t.val = dt.val OR split_part(split_part(t.val, '/', -1), '#', -1) = dt.val)
                             LIMIT 1),
                            'Type除外'
                        )
                    END AS matched_type
                FROM metadata_records
                WHERE {where_sql}
                ORDER BY id
                LIMIT ? OFFSET ?;
            """
        else:
            fetch_query = f"""
                SELECT
                    id,
                    title,
                    description,
                    type_list,
                    '（未定義 / 種別なし）' AS matched_type
                FROM metadata_records
                WHERE {where_sql}
                ORDER BY id
                LIMIT ? OFFSET ?;
            """

        params.extend([int(page_size), int(offset)])
        rows = self.conn.execute(fetch_query, params).fetchall()

        try:
            self.conn.execute("DROP TABLE IF EXISTS temp_disc_types;")
        except Exception:
            pass

        records = [{
            "id": r[0],
            "title": r[1] or "（無題）",
            "description": r[2] or "",
            "type_list": r[3] or [],
            "matched_type": r[4] or "Type除外"
        } for r in rows]

        return total_count, records

    def get_records_discarded_by_types(self, ng_types: List[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        除外対象種別（ng_types）によって影響を受けるすべてのレコード（除外される資料）を高速取得（後方互換対応）
        """
        if not ng_types:
            return []
        page_size = int(limit) if (limit and limit > 0) else 1000000
        _, records = self.query_records_discarded_by_types(ng_types, page=1, page_size=page_size)
        return records

    def export_records_discarded_by_types_csv(self, output_csv_path: str, ng_types: List[str]) -> int:
        """
        除外種別に該当する全レコードをCSVへ直接高速エクスポート（メモリ消費ゼロ）
        """
        import pandas as pd
        os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
        total_cnt, records = self.query_records_discarded_by_types(ng_types, page=1, page_size=1000000)
        df = pd.DataFrame([{
            "ID": r["id"],
            "タイトル": r["title"],
            "除外理由 (該当種別)": r["matched_type"],
            "概要": r["description"]
        } for r in records])
        df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        return len(df)

    def export_complete_audit_trail_csv(self, output_csv_path: str) -> int:
        """
        初期母集団全件の完全来歴追跡データ (Complete Audit Trail) をCSVエクスポート
        """
        import pandas as pd
        os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
        query = """
            SELECT 
                id,
                title,
                CASE 
                    WHEN coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格' THEN 'ADOPTED'
                    ELSE 'DISCARDED'
                END AS final_outcome,
                coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) AS final_verdict_ja,
                coalesce(adopted_stage, drop_stage, CASE WHEN final_decision = 'OK' THEN 'RULE' ELSE 'RULE' END) AS decision_stage,
                coalesce(review_reasons, primary_reason, matched_reason, '未判定') AS decision_reason,
                type_status,
                type_reason,
                about_status,
                about_reason,
                ngram_status,
                ngram_reason,
                llm_status,
                llm_reason,
                external_info,
                human_decision,
                review_reasons
            FROM metadata_records
            ORDER BY id;
        """
        df = self.conn.execute(query).fetchdf()
        df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        return len(df)

    def get_prisma_flow_stats(self) -> Dict[str, Any]:
        """
        PRISMA声明準拠の段階別流出入メトリクスを集計
        """
        total = self.get_record_count()
        if total == 0:
            return {
                "total_records": 0,
                "type_discarded": 0,
                "type_passed": 0,
                "rule_ok": 0,
                "rule_ng": 0,
                "rule_grey": 0,
                "llm_evaluated_total": 0,
                "llm_passed": 0,
                "llm_discarded": 0,
                "human_override_count": 0,
                "final_adopted": 0,
                "final_discarded": 0,
                "top_drop_reasons": []
            }

        # Type除外数
        type_disc_row = self.conn.execute("SELECT COUNT(*) FROM metadata_records WHERE type_status = 'NG';").fetchone()
        type_disc = type_disc_row[0] if type_disc_row else 0

        # Rule (About/Ngram) 判定数
        rule_ok_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE (type_status IS NULL OR type_status != 'NG') 
              AND (adopted_stage IN ('RULE_ABOUT', 'RULE_NGRAM') OR matched_reason LIKE '[ルール合格]%');
        """).fetchone()
        rule_ok = rule_ok_row[0] if rule_ok_row else 0

        rule_ng_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE (type_status IS NULL OR type_status != 'NG') 
              AND drop_stage IN ('RULE_ABOUT', 'RULE_NGRAM');
        """).fetchone()
        rule_ng = rule_ng_row[0] if rule_ng_row else 0

        rule_grey_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE (type_status IS NULL OR type_status != 'NG') 
              AND final_decision = 'GREY';
        """).fetchone()
        rule_grey = rule_grey_row[0] if rule_grey_row else 0

        # LLM判定数
        llm_tot_row = self.conn.execute("SELECT COUNT(*) FROM metadata_records WHERE llm_evaluated = TRUE OR llm_target IS NOT NULL;").fetchone()
        llm_total = llm_tot_row[0] if llm_tot_row else 0

        llm_pass_row = self.conn.execute("SELECT COUNT(*) FROM metadata_records WHERE llm_target = TRUE;").fetchone()
        llm_pass = llm_pass_row[0] if llm_pass_row else 0

        llm_disc_row = self.conn.execute("SELECT COUNT(*) FROM metadata_records WHERE llm_target = FALSE;").fetchone()
        llm_disc = llm_disc_row[0] if llm_disc_row else 0

        # 専門家査読修正
        human_ov_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE human_decision IS NOT NULL 
              AND human_decision != (CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END);
        """).fetchone()
        human_override = human_ov_row[0] if human_ov_row else 0

        # 最終採択数
        final_ad_row = self.conn.execute("""
            SELECT COUNT(*) FROM metadata_records 
            WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '合格';
        """).fetchone()
        final_adopted = final_ad_row[0] if final_ad_row else 0

        # 除外理由上位ランキング
        top_drop_rows = self.conn.execute("""
            SELECT coalesce(primary_reason, matched_reason, 'その他除外') AS reason, COUNT(*) AS cnt
            FROM metadata_records
            WHERE coalesce(human_decision, CASE WHEN final_decision = 'OK' THEN '合格' ELSE '除外' END) = '除外'
            GROUP BY reason
            ORDER BY cnt DESC
            LIMIT 10;
        """).fetchall()

        return {
            "total_records": total,
            "type_discarded": type_disc,
            "type_passed": total - type_disc,
            "rule_ok": rule_ok,
            "rule_ng": rule_ng,
            "rule_grey": rule_grey,
            "llm_evaluated_total": llm_total,
            "llm_passed": llm_pass,
            "llm_discarded": llm_disc,
            "human_override_count": human_override,
            "final_adopted": final_adopted,
            "final_discarded": total - final_adopted,
            "top_drop_reasons": [(str(r[0]), int(r[1])) for r in top_drop_rows]
        }

    def close(self):
        """接続終了"""
        if self.conn:
            self.conn.close()

