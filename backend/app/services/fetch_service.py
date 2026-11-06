# -*- coding: utf-8 -*-
"""
SPARQL取得・LLM推論バックグラウンドジョブ連携サービス
"""
import os
import json
import time
from typing import Dict, Any, Optional, List

from .workspace_service import workspace_service
from .job_manager import job_manager
from ..modules.llm_query_expander import expand_query_with_llm, generate_sparql_queries, optimize_keywords_for_regex
from ..modules.sparql_collector import build_metadata_for_uris, fetch_uris_with_query_func
from ..modules.llm_classifier import run_llm_semantic_classification, run_stage2_llm_classification
from ..modules.duckdb_manager import DuckDBManager
from ..schemas.fetch import QueryExpandResponse


class FetchService:
    def expand_query(self, theme: str, existing_keywords: List[str] = [], provider: str = "gemini", api_key: Optional[str] = None, model: str = "gemini-3.6-flash") -> QueryExpandResponse:
        """LLMによるクエリ拡張"""
        exp = expand_query_with_llm(
            theme=theme,
            existing_keywords=existing_keywords,
            provider=provider,
            api_key=api_key or "",
            model=model
        )
        return QueryExpandResponse(
            keywords=exp.get("keywords", []),
            ndc_codes=exp.get("ndc_codes", []),
            exclude_ndc_codes=exp.get("exclude_ndc_codes", []),
            domain_definition=exp.get("domain_definition", ""),
            title_regex=exp.get("title_regex", ""),
            desc_regex=exp.get("desc_regex", "")
        )

    def start_fetch_job(
        self,
        ws_id: str,
        keywords: List[str],
        ndc_codes: List[str] = [],
        exclude_ndc_codes: List[str] = [],
        title_regex: Optional[str] = None,
        desc_regex: Optional[str] = None,
        domain_definition: Optional[str] = None,
        batch_size: int = 10,
        resume: bool = True
    ) -> str:
        """SPARQL一括取得バックグラウンドジョブを起動"""
        paths = workspace_service.get_paths(ws_id)
        job = job_manager.create_job(ws_id, job_type="sparql_fetch", stage="クエリ生成・URI収集準備中")

        target_uris_csv = paths["PATH_TARGET_URIS"]
        raw_metadata_jsonl = paths["PATH_RAW_METADATA"]
        duckdb_path = paths["PATH_DUCKDB"]

        def _fetch_worker(progress_callback=None, should_stop=None):
            # 1. SPARQLクエリ生成
            if progress_callback:
                progress_callback(0, 0, "SPARQL検索クエリを生成中...")

            # パラメータ保存
            params_file = paths["PATH_CURRENT_PARAMS"]
            params_data = {
                "keywords": keywords,
                "ndc_codes": ndc_codes,
                "exclude_ndc_codes": exclude_ndc_codes,
                "domain_definition": domain_definition,
                "title_regex": title_regex,
                "desc_regex": desc_regex
            }
            with open(params_file, 'w', encoding='utf-8') as f:
                json.dump(params_data, f, ensure_ascii=False, indent=2)

            # 2. URI収集 (既存CSVがある＆レジューム指定時はスキップ可能)
            uris = []
            if resume and os.path.exists(target_uris_csv) and os.path.getsize(target_uris_csv) > 0:
                with open(target_uris_csv, 'r', encoding='utf-8') as f:
                    uris = [line.strip() for line in f if line.strip() and not line.startswith("uri")]
                if progress_callback:
                    progress_callback(len(uris), len(uris), f"既存の対象URIリストをロードしました ({len(uris):,} 件)")
            else:
                queries = generate_sparql_queries(
                    keywords=keywords,
                    ndc_codes=ndc_codes,
                    exclude_ndc_codes=exclude_ndc_codes,
                    title_regex=title_regex,
                    desc_regex=desc_regex
                )
                if progress_callback:
                    progress_callback(0, len(queries), f"SPARQLエンドポイントへ問い合わせ中 ({len(queries)} クエリ)...")

                uris_set = set()
                for q_idx, q in enumerate(queries):
                    if should_stop and should_stop():
                        return
                    res_uris = fetch_uris_with_query_func(q)
                    uris_set.update(res_uris)
                    if progress_callback:
                        progress_callback(len(uris_set), 0, f"SPARQLクエリ {q_idx + 1}/{len(queries)} 完了 (発見URI: {len(uris_set):,} 件)")

                uris = sorted(list(uris_set))
                with open(target_uris_csv, 'w', encoding='utf-8') as f:
                    f.write("uri\n" + "\n".join(uris))

            if not uris:
                raise ValueError("対象となる資料URIが0件でした。検索条件を見直してください。")

            if should_stop and should_stop():
                return

            # 3. CONSTRUCT句による3階層メタデータ再帰取得
            total_uris = len(uris)
            if progress_callback:
                progress_callback(0, total_uris, f"3階層トリプルの再帰取得を開始 ({total_uris:,} 件)...")

            def _collector_cb(cur, tot=None, eta=None):
                if progress_callback:
                    progress_callback(cur, total_uris, f"メタデータ取得進行中 ({cur:,} / {total_uris:,} 件)", eta=eta)

            build_metadata_for_uris(
                target_uris_csv_path=target_uris_csv,
                output_jsonl_path=raw_metadata_jsonl,
                batch_size=batch_size,
                resume=resume,
                progress_callback=_collector_cb,
                should_stop=should_stop
            )

            if should_stop and should_stop():
                return

            # 4. DuckDBへの高速バルクインポート
            if progress_callback:
                progress_callback(total_uris, total_uris, "DuckDB高速エンジンにインポート中...")

            with DuckDBManager(duckdb_path) as db:
                db.import_jsonl(raw_metadata_jsonl)

            if progress_callback:
                progress_callback(total_uris, total_uris, f"全工程完了！初期データセット {total_uris:,} 件をインポートしました。")

        job_manager.run_in_background(job.job_id, _fetch_worker)
        return job.job_id

    def start_llm_job(
        self,
        ws_id: str,
        domain_definition: str = "日本の古典籍における楽譜・音楽資料",
        provider: str = "gemini",
        api_base: str = "http://localhost:1234/v1",
        api_key: Optional[str] = "",
        model: str = "gemini-3.6-flash",
        max_workers: int = 2,
        limit: Optional[int] = None,
        stage2: bool = False
    ) -> str:
        """LLMセマンティック推論ジョブを起動"""
        paths = workspace_service.get_paths(ws_id)
        target_jsonl = paths["PATH_TARGET_FOR_LLM"]
        llm_judgments = paths["PATH_LLM_JUDGMENTS"]
        duckdb_path = paths["PATH_DUCKDB"]

        job_type = "llm_stage2" if stage2 else "llm_classification"
        job = job_manager.create_job(ws_id, job_type=job_type, stage="LLMセマンティック推論準備中")

        def _llm_worker(progress_callback=None, should_stop=None):
            def _cb(cur, tot=None, eta=None):
                if progress_callback:
                    progress_callback(cur, tot, f"LLM判定進行中 ({cur:,} / {tot:,} 件)", eta=eta)

            if stage2:
                run_stage2_llm_classification(
                    judgments_jsonl_path=llm_judgments,
                    domain_definition=domain_definition,
                    provider=provider,
                    api_base=api_base,
                    api_key=api_key or "",
                    model=model,
                    max_workers=max_workers,
                    progress_callback=_cb,
                    should_stop=should_stop
                )
            else:
                run_llm_semantic_classification(
                    input_jsonl_path=target_jsonl,
                    output_judgments_path=llm_judgments,
                    domain_definition=domain_definition,
                    provider=provider,
                    api_base=api_base,
                    api_key=api_key or "",
                    model=model,
                    limit=limit,
                    max_workers=max_workers,
                    progress_callback=_cb,
                    should_stop=should_stop
                )

            if should_stop and should_stop():
                return

            # DuckDB に判定結果を同期
            if progress_callback:
                progress_callback(100, 100, "DuckDBに推論結果を同期中...")

            with DuckDBManager(duckdb_path) as db:
                db.sync_llm_judgments(llm_judgments)

            if progress_callback:
                progress_callback(100, 100, "LLMセマンティック推論が完了しました。")

        job_manager.run_in_background(job.job_id, _llm_worker)
        return job.job_id


fetch_service = FetchService()

