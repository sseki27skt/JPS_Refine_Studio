# -*- coding: utf-8 -*-
"""
LLMセマンティック推論 API
"""
from fastapi import APIRouter, HTTPException

from ..schemas.fetch import StartLlmRequest
from ..services.fetch_service import fetch_service

router = APIRouter(prefix="/api/workspaces/{ws_id}/llm", tags=["llm"])


@router.post("/start")
def start_llm_classification(ws_id: str, req: StartLlmRequest):
    """判定保留群（Grey群）に対するLLMセマンティック推論ジョブを開始"""
    try:
        job_id = fetch_service.start_llm_job(
            ws_id=ws_id,
            domain_definition=req.domain_definition,
            provider=req.provider,
            api_base=req.api_base,
            api_key=req.api_key or "",
            model=req.model,
            max_workers=req.max_workers,
            limit=req.limit,
            stage2=req.stage2
        )
        return {"job_id": job_id, "message": "LLMセマンティック適合判定ジョブを開始しました。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM推論ジョブ起動エラー: {e}")

