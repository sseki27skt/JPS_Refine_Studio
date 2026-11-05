# -*- coding: utf-8 -*-
"""
レコード管理・査読ポータルサービス
"""
import os
import math
from typing import Dict, Any, Optional, List

from .workspace_service import workspace_service
from ..modules.duckdb_manager import DuckDBManager
from ..schemas.record import PaginatedRecordsResponse, RecordItem, ReviewMetrics, FacetsResponse


class RecordService:
    def _get_db(self, ws_id: str) -> DuckDBManager:
        paths = workspace_service.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        return DuckDBManager(duckdb_path)

    def query_records(
        self,
        ws_id: str,
        filter_status: str = "すべて",
        search_query: str = "",
        stage: Optional[str] = None,
        target_type: Optional[str] = None,
        provider: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        has_image: Optional[bool] = None,
        creator: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        filter_source: Optional[str] = None
    ) -> PaginatedRecordsResponse:
        paths = workspace_service.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path) or os.path.getsize(duckdb_path) == 0:
            return PaginatedRecordsResponse(total=0, page=page, page_size=page_size, total_pages=0, records=[])

        with self._get_db(ws_id) as db:
            total, raw_records = db.query_records(
                filter_status=filter_status,
                search_query=search_query,
                stage=stage,
                target_type=target_type,
                provider=provider,
                year_from=year_from,
                year_to=year_to,
                has_image=has_image,
                creator=creator,
                page=page,
                page_size=page_size,
                filter_source=filter_source
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 0
        items = [RecordItem(**r) for r in raw_records]
        return PaginatedRecordsResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            records=items
        )

    def get_review_metrics(self, ws_id: str) -> ReviewMetrics:
        paths = workspace_service.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return ReviewMetrics()

        with self._get_db(ws_id) as db:
            m = db.get_review_metrics()
            return ReviewMetrics(
                total=m.get("total", 0),
                passed_cnt=m.get("passed_cnt", 0),
                reject_cnt=m.get("reject_cnt", 0),
                override_cnt=m.get("override_cnt", 0),
                null_cnt=m.get("null_cnt", 0)
            )

    def get_facets(self, ws_id: str) -> FacetsResponse:
        paths = workspace_service.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return FacetsResponse()

        with self._get_db(ws_id) as db:
            stats = db.get_facets_stats()
            return FacetsResponse(
                top_providers=stats.get("top_providers", []),
                era_distribution=stats.get("era_distribution", []),
                has_image_count=stats.get("has_image_count", 0),
                no_image_count=stats.get("no_image_count", 0)
            )

    def update_decision(self, ws_id: str, record_id: str, decision: Optional[str]) -> bool:
        paths = workspace_service.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]
        if not os.path.exists(duckdb_path):
            return False

        with self._get_db(ws_id) as db:
            db.set_human_decision(record_id, decision)

        # 確定JSONLへ即時オートセーブ同期
        verified_path = paths["PATH_VERIFIED_JSONL"]
        try:
            with self._get_db(ws_id) as db:
                db.export_human_verified_data(verified_path)
        except Exception:
            pass
        return True

    def export_verified(self, ws_id: str) -> int:
        paths = workspace_service.get_paths(ws_id)
        verified_path = paths["PATH_VERIFIED_JSONL"]
        with self._get_db(ws_id) as db:
            return db.export_human_verified_data(verified_path)


record_service = RecordService()

