# -*- coding: utf-8 -*-
"""
JS-Refine Studio - About キーワード超高速インメモリ転置インデックス
18万レコードの主題キーワード共起関係とリアルタイム残存件数を 0.01〜0.02秒 で計算
"""

import os
import json
from collections import defaultdict
from typing import Dict, Set, Tuple, List, Optional
import streamlit as st


from modules.ngram_filter import clean_title_text


class AboutInvertedIndex:
    """
    主題キーワードの転置インデックス (Keyword -> Set of Record IDs)
    インメモリ set 演算により、数千件のNGルールに対しても数ミリ秒で残存件数を集計可能。
    さらに Step 2-C のタイトル除外ルールとも完全連携し、双方向リアルタイム連動を実現。
    """
    def __init__(self, kw_to_rec_ids: Dict[str, Set[int]], total_records: int, rec_id_to_title: Optional[Dict[int, str]] = None):
        self.kw_to_rec_ids = kw_to_rec_ids
        self.total_records = total_records
        self.all_kws = list(kw_to_rec_ids.keys())
        self.rec_id_to_title = rec_id_to_title or {}

    def compute_discarded_records(self, ng_keywords: Set[str]) -> Set[int]:
        """
        NGキーワード群に該当するレコードIDの集合を高速算出 (約0.003秒)
        """
        if not ng_keywords:
            return set()
        discarded = set()
        for kw in ng_keywords:
            recs = self.kw_to_rec_ids.get(kw)
            if recs:
                discarded.update(recs)
        return discarded

    def compute_title_discarded_records(self, ngram_ng_keywords: Set[str]) -> Set[int]:
        """
        Step 2-C のタイトルNGルールに一致するレコードIDの集合を高速算出 (約0.01秒)
        正規化済みタイトルと照合し、表記揺れによる除外漏れを完全防止
        """
        if not ngram_ng_keywords or not self.rec_id_to_title:
            return set()

        # 冗長な長いパターンを整理して最短パターンにスリム化
        minimal_ng = []
        for w in sorted(list(ngram_ng_keywords), key=len):
            w_clean = clean_title_text(w)
            if len(w_clean) >= 1 and not any(sub in w_clean for sub in minimal_ng):
                minimal_ng.append(w_clean)

        discarded = set()
        for rid, t_clean in self.rec_id_to_title.items():
            if any(nw in t_clean for nw in minimal_ng):
                discarded.add(rid)
        return discarded

    def compute_active_counts(self, discarded_rec_ids: Set[int], target_keywords: Optional[List[str]] = None) -> Dict[str, int]:
        """
        除外レコード群を差し引いた、各キーワードの真の残存出現件数を瞬時に計算 (約0.01秒)
        """
        kws_to_eval = target_keywords if target_keywords is not None else self.all_kws
        counts = {}
        for kw in kws_to_eval:
            recs = self.kw_to_rec_ids.get(kw)
            if not recs:
                counts[kw] = 0
            else:
                counts[kw] = len(recs - discarded_rec_ids)
        return counts


@st.cache_resource(show_spinner="主題キーワードの高速インデックスを構築中...")
def get_about_inverted_index(duckdb_path: str, fallback_jsonl_path: str, exclude_ng_types: bool = True) -> AboutInvertedIndex:
    """
    DuckDB または JSONL から主題キーワードの転置インデックスをメモリ上に1回だけ構築。
    以後は st.cache_resource によりゼロ秒で参照され、超高速な差分計算を実現します。
    """
    kw_to_recs = defaultdict(set)
    rec_id_to_title = {}
    total_recs = 0

    # 1. DuckDB から高速一括ロード (0.2〜0.4秒)
    if duckdb_path and os.path.exists(duckdb_path):
        try:
            from modules.duckdb_manager import get_duckdb_manager
            db = get_duckdb_manager(duckdb_path)
            where_sql = "(type_status IS NULL OR type_status != 'NG') AND about_list IS NOT NULL" if exclude_ng_types else "about_list IS NOT NULL"
            query = f"""
                SELECT kw, rowid
                FROM (
                    SELECT rowid, unnest(about_list) as kw
                    FROM metadata_records
                    WHERE {where_sql}
                )
                WHERE kw IS NOT NULL AND trim(kw) != '';
            """
            rows = db.conn.execute(query).fetchall()
            for kw, rid in rows:
                kw_to_recs[str(kw)].add(int(rid))
            tot_row = db.conn.execute(f"SELECT COUNT(*) FROM metadata_records WHERE {where_sql};").fetchone()
            total_recs = tot_row[0] if tot_row else 0

            # タイトル文字列も同時にキャッシュ (約0.05秒)
            t_rows = db.conn.execute(f"SELECT rowid, title FROM metadata_records WHERE {where_sql} AND title IS NOT NULL;").fetchall()
            rec_id_to_title = {int(r[0]): clean_title_text(str(r[1])) for r in t_rows if r[1]}

            if kw_to_recs:
                return AboutInvertedIndex(dict(kw_to_recs), total_recs, rec_id_to_title)
        except Exception:
            pass

    # 2. フォールバック: JSONL からロード
    if fallback_jsonl_path and os.path.exists(fallback_jsonl_path):
        rec_idx = 0
        with open(fallback_jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    t_val = item.get("schema:name", item.get("title", ""))
                    if t_val:
                        rec_id_to_title[rec_idx] = clean_title_text(str(t_val))

                    about_val = item.get("schema:about", item.get("about", []))
                    if isinstance(about_val, str):
                        about_list = [about_val]
                    elif isinstance(about_val, list):
                        about_list = about_val
                    else:
                        about_list = []
                    for a in about_list:
                        kw_str = a.get("schema:name", a.get("name", "")) if isinstance(a, dict) else str(a)
                        kw_str = kw_str.strip()
                        if kw_str:
                            kw_to_recs[kw_str].add(rec_idx)
                    rec_idx += 1
                except Exception:
                    continue
        total_recs = rec_idx
        return AboutInvertedIndex(dict(kw_to_recs), total_recs, rec_id_to_title)

    return AboutInvertedIndex({}, 0, {})


@st.cache_data(show_spinner=False)
def get_cached_title_discarded_records(_about_idx: AboutInvertedIndex, ngram_ng_tuple: Tuple[str, ...]) -> Set[int]:
    """
    Step 2-C のタイトル除外ルールに一致するレコードIDの集合を高速キャッシュ (初回のみ計算、以後はゼロ秒参照)
    ピルクリック時の18万行フルスキャンを完全防止。
    """
    if not ngram_ng_tuple or _about_idx is None:
        return set()
    return _about_idx.compute_title_discarded_records(set(ngram_ng_tuple))
