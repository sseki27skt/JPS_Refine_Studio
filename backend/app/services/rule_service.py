# -*- coding: utf-8 -*-
"""
フィルタ・クレンジングルール管理および高度クラスタリングサービス
- NDC 3段階階層ツリークラスタリング
- NDL典拠 セマンティック種別分離
- タイトルN-gram 接尾辞（Suffix）クラスタリング
- ルール影響レコード完全一覧（ページネーション・衝突警告付き）
- ルール一括適用バックグラウンドジョブ
"""
import os
import re
import json
import math
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple

from .workspace_service import workspace_service
from .job_manager import job_manager
from ..modules.duckdb_manager import DuckDBManager
from ..modules.rule_filter import load_type_rules, save_type_rules
from ..modules.ndc_utils import (
    extract_ndc_number,
    resolve_ndc_label,
    extract_ndlc_code,
    resolve_ndlc_label,
    extract_ndl_auth_info,
    resolve_ndlna_label,
    prefetch_about_keywords_batch,
    fetch_ndc_sparql_batch
)
from ..modules.file_utils import safe_save_json
from ..schemas.rule import RuleImpactResponse, ClusterItem, RuleApplyResponse
from ..schemas.record import RecordItem


class RuleService:
    def _get_paths(self, ws_id: str) -> Dict[str, str]:
        return workspace_service.get_paths(ws_id)

    def _get_db(self, ws_id: str) -> DuckDBManager:
        paths = self._get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        return DuckDBManager(duckdb_path)

    # =========================================================================
    # 1. Type ルール
    # =========================================================================
    def get_type_rules_and_stats(self, ws_id: str) -> Dict[str, Any]:
        paths = self._get_paths(ws_id)
        type_rules_path = paths["PATH_TYPE_RULES"]
        duckdb_path = paths["PATH_DUCKDB"]

        rules = load_type_rules(type_rules_path) if os.path.exists(type_rules_path) else {"NG": [], "OK": []}
        stats = []
        if os.path.exists(duckdb_path):
            with self._get_db(ws_id) as db:
                stats = db.get_type_stats()

        return {
            "rules": rules,
            "stats": stats
        }

    def save_type_rules(self, ws_id: str, ng_list: List[str], ok_list: List[str] = []) -> bool:
        paths = self._get_paths(ws_id)
        type_rules_path = paths["PATH_TYPE_RULES"]
        rules = {"NG": sorted(list(set(ng_list))), "OK": sorted(list(set(ok_list)))}
        save_type_rules(type_rules_path, rules)
        return True

    # =========================================================================
    # 2. About ルール & 高度クラスタリング
    # =========================================================================
    def get_about_rules(self, ws_id: str) -> Dict[str, str]:
        paths = self._get_paths(ws_id)
        about_rules_path = paths["PATH_ABOUT_RULES"]
        if os.path.exists(about_rules_path):
            try:
                with open(about_rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_about_rules(self, ws_id: str, rules: Dict[str, str]) -> bool:
        paths = self._get_paths(ws_id)
        about_rules_path = paths["PATH_ABOUT_RULES"]
        safe_save_json(about_rules_path, rules)
        return True

    def get_about_clusters(self, ws_id: str) -> List[ClusterItem]:
        """
        DuckDBから全Aboutキーワードを取得し、
        ① NDC 3段階階層ツリー、② NDL典拠の種別分離、③ NDLC、④ 階層区切りで構造化
        """
        paths = self._get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return []

        with self._get_db(ws_id) as db:
            ranking = db.get_about_keyword_counts(limit=3000, exclude_ng_types=True)

        if not ranking:
            return []

        # 事前一括解決 (NDC & NDL典拠)
        all_kws = [k for k, _ in ranking[:300]]
        prefetch_about_keywords_batch(all_kws)

        ndc_items = []
        ndlc_items = []
        ndlsh_items = []
        ndlna_items = []
        prefix_items = defaultdict(list)
        unassigned = []

        for kw, cnt in ranking:
            # A. NDCコード
            ndc_num = extract_ndc_number(kw)
            if ndc_num:
                ndc_items.append((ndc_num, kw, cnt))
                continue

            # B. NDL 典拠
            auth_info = extract_ndl_auth_info(kw)
            if auth_info:
                aid, atype = auth_info
                if atype == "ndlsh":
                    ndlsh_items.append((kw, cnt, aid))
                else:
                    ndlna_items.append((kw, cnt, aid))
                continue

            # C. NDLC コード
            ndlc_code = extract_ndlc_code(kw)
            if ndlc_code:
                ndlc_items.append((ndlc_code, kw, cnt))
                continue

            # D. 階層区切り記号
            if "--" in kw:
                parts = kw.split("--")
                parent = parts[0].strip()
                prefix_items[parent].append((kw, cnt))
            else:
                m = re.match(r'^(.*?)(?:[/:\s_･]+)(.+)$', kw)
                if m and len(m.group(1).strip()) >= 2:
                    parent = m.group(1).strip()
                    prefix_items[parent].append((kw, cnt))
                else:
                    unassigned.append((kw, cnt))

        clusters: List[ClusterItem] = []
        c_idx = 0

        # -------------------------------------------------------------
        # ① NDC 3段階階層ツリークラスタリング (類 ＞ 綱 ＞ 目)
        # -------------------------------------------------------------
        ndc_classes = defaultdict(lambda: defaultdict(list))  # 類(1桁) -> 綱(2桁) -> [ (kw, cnt) ]
        for ndc_num, kw, cnt in ndc_items:
            cls1 = ndc_num[0]
            cls2 = ndc_num[:2] if len(ndc_num) >= 2 else (ndc_num + "0")
            ndc_classes[cls1][cls2].append((kw, cnt, ndc_num))

        cls1_labels = {
            "0": "総記", "1": "哲学・宗教", "2": "歴史・地理", "3": "社会科学", "4": "自然科学",
            "5": "技術・工学", "6": "産業", "7": "芸術・美術・音楽", "8": "言語", "9": "文学"
        }

        for c1, c2_map in sorted(ndc_classes.items()):
            c1_label = cls1_labels.get(c1, f"{c1}類")
            c1_total = sum(c for c2_items in c2_map.values() for _, c, _ in c2_items)
            c1_kws = [k for c2_items in c2_map.values() for k, _, _ in c2_items]

            sub_clusters = []
            for c2, items in sorted(c2_map.items()):
                c2_total = sum(c for _, c, _ in items)
                lbl2, _, _ = resolve_ndc_label(c2)
                sub_clusters.append({
                    "id": f"ndc_sub_{c2}",
                    "name": f"【綱 {c2}】{lbl2 or ''}",
                    "count": c2_total,
                    "keywords": [k for k, _, _ in items]
                })

            clusters.append(ClusterItem(
                cluster_id=f"cl_ndc_tree_{c_idx}",
                name=f"NDC分類 {c1}類 [{c1_label}]",
                category="ndc_tree",
                keywords=c1_kws,
                total_count=c1_total,
                resolved_label=c1_label,
                sub_clusters=sub_clusters
            ))
            c_idx += 1

        # -------------------------------------------------------------
        # ② NDL 典拠の種別分離 (普通件名 NDLSH vs 人名・団体名 NDLNA)
        # -------------------------------------------------------------
        if ndlsh_items:
            tot = sum(c for _, c, _ in ndlsh_items)
            clusters.append(ClusterItem(
                cluster_id=f"cl_ndlsh_{c_idx}",
                name="NDLSH 普通件名 (ジャンル・概念・形態)",
                category="ndlsh_topic",
                keywords=[k for k, _, _ in ndlsh_items],
                total_count=tot
            ))
            c_idx += 1

        if ndlna_items:
            tot = sum(c for _, c, _ in ndlna_items)
            clusters.append(ClusterItem(
                cluster_id=f"cl_ndlna_{c_idx}",
                name="NDLNA 人名・著者・団体名典拠",
                category="ndlna_person",
                keywords=[k for k, _, _ in ndlna_items],
                total_count=tot
            ))
            c_idx += 1

        # -------------------------------------------------------------
        # ③ NDLC 分類
        # -------------------------------------------------------------
        if ndlc_items:
            ndlc_grouped = defaultdict(list)
            for code, kw, cnt in ndlc_items:
                ndlc_grouped[code].append((kw, cnt))

            for code, items in sorted(ndlc_grouped.items()):
                tot = sum(c for _, c in items)
                lbl = resolve_ndlc_label(code)
                tag = f" [{lbl}]" if lbl else ""
                clusters.append(ClusterItem(
                    cluster_id=f"cl_ndlc_{c_idx}",
                    name=f"NDLC分類: {code}{tag}",
                    category="general",
                    keywords=[k for k, _ in items],
                    total_count=tot,
                    resolved_label=lbl
                ))
                c_idx += 1

        # -------------------------------------------------------------
        # ④ 階層プレフィックス
        # -------------------------------------------------------------
        for pkey, items in sorted(prefix_items.items(), key=lambda x: sum(c for _, c in x[1]), reverse=True):
            if len(items) >= 2:
                tot = sum(c for _, c in items)
                clusters.append(ClusterItem(
                    cluster_id=f"cl_prefix_{c_idx}",
                    name=f"階層: {pkey}",
                    category="general",
                    keywords=[k for k, _ in items],
                    total_count=tot
                ))
                c_idx += 1

        return clusters

    # =========================================================================
    # 3. N-gram ルール & 接尾辞クラスタリング
    # =========================================================================
    def get_ngram_rules(self, ws_id: str) -> Dict[str, str]:
        paths = self._get_paths(ws_id)
        ngram_rules_path = paths["PATH_NGRAM_RULES"]
        if os.path.exists(ngram_rules_path):
            try:
                with open(ngram_rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_ngram_rules(self, ws_id: str, rules: Dict[str, str]) -> bool:
        paths = self._get_paths(ws_id)
        ngram_rules_path = paths["PATH_NGRAM_RULES"]
        safe_save_json(ngram_rules_path, rules)
        return True

    def get_ngram_rankings_and_clusters(self, ws_id: str, min_n: int = 2, max_n: int = 4) -> Dict[str, Any]:
        """
        N-gram出現頻度ランキングとともに、
        接尾辞（Suffix: 〜譜、〜集、〜図、〜録、〜論、〜日記等）で束ねたクラスタを返却
        """
        paths = self._get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return {"rankings": {}, "suffix_clusters": []}

        with self._get_db(ws_id) as db:
            raw_ngrams = db.extract_ngrams(min_n=min_n, max_n=max_n, top_k=200)

        # 接尾辞クラスタリング
        target_suffixes = ["譜", "集", "録", "図", "絵", "論", "記", "書", "抄", "選", "誌", "目録", "手引", "入門"]
        suffix_map = defaultdict(list)
        all_words = []

        formatted_rankings = {}
        for n_val, items in raw_ngrams.items():
            formatted_rankings[str(n_val)] = [{"word": w, "count": c} for w, c in items]
            for w, c in items:
                all_words.append((w, c))
                for sfx in target_suffixes:
                    if w.endswith(sfx) and len(w) >= 2:
                        suffix_map[sfx].append((w, c))
                        break

        suffix_clusters = []
        c_idx = 0
        for sfx in target_suffixes:
            items = suffix_map.get(sfx, [])
            if items:
                items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
                tot = sum(c for _, c in items_sorted)
                suffix_clusters.append({
                    "cluster_id": f"cl_sfx_{c_idx}",
                    "name": f"定型末尾: 『〜{sfx}』",
                    "suffix": sfx,
                    "total_count": tot,
                    "items": [{"word": w, "count": c} for w, c in items_sorted]
                })
                c_idx += 1

        return {
            "rankings": formatted_rankings,
            "suffix_clusters": suffix_clusters
        }

    # =========================================================================
    # 4. ルール影響レコード完全一覧 (ページネーション & 衝突警告)
    # =========================================================================
    def query_impact_records(
        self,
        ws_id: str,
        rule_type: str,
        rule_value: str,
        rule_action: str = "NG",
        page: int = 1,
        page_size: int = 50,
        search_query: str = "",
        warning_only: bool = False
    ) -> RuleImpactResponse:
        paths = self._get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return RuleImpactResponse(total_impact_count=0, warning_conflict_count=0, page=page, page_size=page_size, total_pages=0, records=[])

        with self._get_db(ws_id) as db:
            total_cnt, conflict_cnt, raw_records = db.query_impact_records(
                rule_type=rule_type,
                rule_value=rule_value,
                rule_action=rule_action,
                page=page,
                page_size=page_size,
                search_query=search_query,
                warning_only=warning_only
            )

        total_pages = math.ceil(total_cnt / page_size) if total_cnt > 0 else 0
        items = [RecordItem(**r) for r in raw_records]
        return RuleImpactResponse(
            total_impact_count=total_cnt,
            warning_conflict_count=conflict_cnt,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            records=items
        )

    # =========================================================================
    # 5. ルール一括適用ジョブの起動
    # =========================================================================
    def start_apply_rules_job(self, ws_id: str) -> RuleApplyResponse:
        paths = self._get_paths(ws_id)
        about_rules = self.get_about_rules(ws_id)
        ngram_rules = self.get_ngram_rules(ws_id)
        type_rules_data = self.get_type_rules_and_stats(ws_id).get("rules", {})
        ng_types = type_rules_data.get("NG", [])

        job = job_manager.create_job(ws_id, job_type="apply_rules", stage="ルール一括適用開始")

        def _worker_task(progress_callback=None, should_stop=None):
            if progress_callback:
                progress_callback(10, 100, "DuckDB接続確立中...")
            with DuckDBManager(paths["PATH_DUCKDB"]) as db:
                if should_stop and should_stop():
                    return
                # 1. Typeフィルタ適用
                if ng_types:
                    if progress_callback:
                        progress_callback(30, 100, f"Type除外ルール適用中 ({len(ng_types)}種別)...")
                    db.apply_type_filter_fast(ng_types)

                if should_stop and should_stop():
                    return

                # 2. About & Ngram 高速一括適用
                if progress_callback:
                    progress_callback(60, 100, "AboutおよびN-gramルールをDuckDBに一括適用中...")
                res = db.apply_rules_fast(about_rules, ngram_rules)

                # 3. 中間データセットのエクスポート
                if progress_callback:
                    progress_callback(90, 100, "LLM推論対象（Grey群）および中間データを出力中...")
                db.export_split_datasets(
                    output_target_for_llm_jsonl=paths["PATH_TARGET_FOR_LLM"],
                    output_confirmed_ok_jsonl=paths["PATH_CONFIRMED_OK"],
                    output_discarded_csv=paths["PATH_DISCARDED_RULES"]
                )
                if progress_callback:
                    progress_callback(100, 100, f"ルール適用完了: OK {res.get('ok', 0)}件 / NG {res.get('ng', 0)}件 / 保留 {res.get('grey', 0)}件")

        job_manager.run_in_background(job.job_id, _worker_task)
        return RuleApplyResponse(job_id=job.job_id, message="ルール一括適用ジョブを開始しました。")


rule_service = RuleService()

