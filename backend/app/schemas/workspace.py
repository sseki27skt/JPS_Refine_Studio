# -*- coding: utf-8 -*-
"""
ワークスペース関連の Pydantic スキーマ
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class WorkspaceMeta(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    research_theme: Optional[str] = ""
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""
    disk_size_bytes: Optional[int] = 0
    has_raw_metadata: bool = False
    has_duckdb: bool = False
    cloned_from: Optional[str] = None


class WorkspaceCreateRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    research_theme: Optional[str] = ""
    clone_from: Optional[str] = None


class DashboardStats(BaseModel):
    step1_raw: int = 0
    step2a_type_survivors: int = 0
    step2b_about_survivors: int = 0
    step2c_ngram_survivors: int = 0
    step3_llm_evaluated: int = 0
    step4_human_reviewed: int = 0
    step5_export_ready: int = 0
    total_records: int = 0
    active_job: Optional[Dict[str, Any]] = None


class SnapshotCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""


class SnapshotMeta(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    created_at: str
    metrics: Dict[str, Any] = {}

