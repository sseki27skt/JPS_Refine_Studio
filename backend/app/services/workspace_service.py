# -*- coding: utf-8 -*-
"""
ワークスペース操作・スナップショット・ダッシュボード集計サービス
"""
import os
import json
from typing import List, Dict, Any, Optional

from ..config import PROJECT_ROOT, WORKSPACES_DIR, VIEWER_DIR
from ..modules.workspace_manager import WorkspaceManager
from ..modules.duckdb_manager import DuckDBManager
from ..schemas.workspace import WorkspaceMeta, DashboardStats, SnapshotMeta
from .job_manager import job_manager


class WorkspaceService:
    def __init__(self):
        self.wm = WorkspaceManager(project_root=str(PROJECT_ROOT))

    def list_workspaces(self) -> List[WorkspaceMeta]:
        raw_list = self.wm.list_workspaces()
        results = []
        for w in raw_list:
            results.append(WorkspaceMeta(
                id=w.get("id", ""),
                name=w.get("name", ""),
                description=w.get("description", ""),
                research_theme=w.get("research_theme", ""),
                created_at=w.get("created_at", ""),
                updated_at=w.get("updated_at", ""),
                disk_size_bytes=w.get("disk_size_bytes", 0),
                has_raw_metadata=w.get("has_raw_metadata", False),
                has_duckdb=w.get("has_duckdb", False),
                cloned_from=w.get("cloned_from")
            ))
        return results

    def get_workspace(self, ws_id: str) -> Optional[WorkspaceMeta]:
        w = self.wm.get_workspace(ws_id)
        if not w:
            return None
        return WorkspaceMeta(
            id=w.get("id", ""),
            name=w.get("name", ""),
            description=w.get("description", ""),
            research_theme=w.get("research_theme", ""),
            created_at=w.get("created_at", ""),
            updated_at=w.get("updated_at", ""),
            disk_size_bytes=w.get("disk_size_bytes", 0),
            has_raw_metadata=w.get("has_raw_metadata", False),
            has_duckdb=w.get("has_duckdb", False),
            cloned_from=w.get("cloned_from")
        )

    def create_workspace(self, ws_id: str, name: str, description: str = "", research_theme: str = "", clone_from: Optional[str] = None) -> WorkspaceMeta:
        meta = self.wm.create_workspace(
            ws_id=ws_id,
            name=name,
            description=description,
            research_theme=research_theme,
            clone_from=clone_from
        )
        return WorkspaceMeta(**meta)

    def delete_workspace(self, ws_id: str) -> bool:
        return self.wm.delete_workspace(ws_id)

    def get_paths(self, ws_id: str) -> Dict[str, str]:
        return self.wm.get_workspace_paths(ws_id)

    def get_dashboard_stats(self, ws_id: str) -> DashboardStats:
        paths = self.get_paths(ws_id)
        duckdb_path = paths["PATH_DUCKDB"]

        stats = DashboardStats()
        if os.path.exists(duckdb_path) and os.path.getsize(duckdb_path) > 0:
            try:
                with DuckDBManager(duckdb_path) as db:
                    flow = db.get_prisma_flow_stats() or {}
                    stats.total_records = flow.get("total_records", 0)
                    stats.step1_raw = flow.get("step1_raw", stats.total_records)
                    stats.step2a_type_survivors = flow.get("step2a_type_survivors", 0)
                    stats.step2b_about_survivors = flow.get("step2b_about_survivors", 0)
                    stats.step2c_ngram_survivors = flow.get("step2c_ngram_survivors", 0)
                    stats.step3_llm_evaluated = flow.get("step3_llm_evaluated", 0)
                    stats.step4_human_reviewed = flow.get("step4_human_reviewed", 0)
                    stats.step5_export_ready = flow.get("step5_export_ready", 0)
            except Exception:
                pass

        # アクティブなジョブがあれば含める
        active_job = job_manager.get_active_job_for_workspace(ws_id)
        if active_job:
            stats.active_job = active_job.model_dump()

        return stats

    def create_snapshot(self, ws_id: str, name: str, description: str = "") -> SnapshotMeta:
        snap_meta = self.wm.save_snapshot(ws_id, name, description)
        return SnapshotMeta(
            id=snap_meta.get("id", ""),
            name=snap_meta.get("name", ""),
            description=snap_meta.get("description", ""),
            created_at=snap_meta.get("created_at", ""),
            metrics=snap_meta.get("metrics", {})
        )

    def list_snapshots(self, ws_id: str) -> List[SnapshotMeta]:
        raw_snaps = self.wm.list_snapshots(ws_id)
        return [
            SnapshotMeta(
                id=s.get("id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                created_at=s.get("created_at", ""),
                metrics=s.get("metrics", {})
            )
            for s in raw_snaps
        ]

    def restore_snapshot(self, ws_id: str, snap_id: str) -> Dict[str, Any]:
        return self.wm.restore_snapshot(ws_id, snap_id)


workspace_service = WorkspaceService()

