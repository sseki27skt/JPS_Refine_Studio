# -*- coding: utf-8 -*-
"""
ジョブ管理・SSEストリーミング関連の Pydantic スキーマ
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel


class JobStatus(str, Enum):
    IDLE = "IDLE"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class JobProgress(BaseModel):
    job_id: str
    workspace_id: str
    type: str  # "sparql_fetch", "llm_classification", "apply_rules" 等
    stage: str = "準備中"
    status: JobStatus = JobStatus.PENDING
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    eta_seconds: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

