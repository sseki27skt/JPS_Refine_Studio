# -*- coding: utf-8 -*-
"""
ジョブ管理・SSEストリーミング配信 API
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas.job import JobProgress
from ..services.job_manager import job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=List[JobProgress])
def list_jobs(workspace_id: Optional[str] = None):
    """ジョブ一覧を取得"""
    return job_manager.list_jobs(workspace_id)


@router.get("/{job_id}", response_model=JobProgress)
def get_job(job_id: str):
    """特定ジョブの最新進捗を取得"""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="指定されたジョブが見つかりません。")
    return job


@router.get("/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """
    ジョブのリアルタイム進捗を SSE (Server-Sent Events) でストリーミング配信
    ブラウザの EventSource でそのまま受信可能。
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="指定されたジョブが見つかりません。")

    return StreamingResponse(
        job_manager.subscribe(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/{job_id}/stop")
def stop_job(job_id: str):
    """実行中ジョブの中断をリクエスト"""
    success = job_manager.request_stop(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="ジョブが見つからないか、既に終了しています。")
    return {"message": f"ジョブ '{job_id}' の中断を要求しました。"}

