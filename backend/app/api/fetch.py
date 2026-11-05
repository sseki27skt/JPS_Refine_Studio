# -*- coding: utf-8 -*-
"""
SPARQL取得・クエリ拡張 API
"""
from fastapi import APIRouter, HTTPException

from ..schemas.fetch import QueryExpandRequest, QueryExpandResponse, StartFetchRequest
from ..services.fetch_service import fetch_service

router = APIRouter(prefix="/api/workspaces/{ws_id}/fetch", tags=["fetch"])


@router.post("/expand-query", response_model=QueryExpandResponse)
def expand_query(ws_id: str, req: QueryExpandRequest):
    """LLMを用いた検索クエリ拡張（キーワード・NDC・正規表現の自動生成）"""
    try:
        return fetch_service.expand_query(
            theme=req.theme,
            existing_keywords=req.existing_keywords,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"クエリ拡張エラー: {e}")


@router.post("/start")
def start_fetch(ws_id: str, req: StartFetchRequest):
    """SPARQL一括取得ジョブを非同期バックグラウンドで開始"""
    try:
        job_id = fetch_service.start_fetch_job(
            ws_id=ws_id,
            keywords=req.keywords,
            ndc_codes=req.ndc_codes,
            exclude_ndc_codes=req.exclude_ndc_codes,
            title_regex=req.title_regex,
            desc_regex=req.desc_regex,
            domain_definition=req.domain_definition,
            batch_size=req.batch_size,
            resume=req.resume
        )
        return {"job_id": job_id, "message": "SPARQLメタデータ一括取得ジョブを開始しました。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取得ジョブ起動エラー: {e}")

