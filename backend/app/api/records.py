# -*- coding: utf-8 -*-
"""
レコード管理・査読ポータル API (高速ページネーション & ファセット対応)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from ..schemas.record import (
    PaginatedRecordsResponse, ReviewMetrics, FacetsResponse,
    UpdateDecisionRequest
)
from ..services.record_service import record_service

router = APIRouter(prefix="/api/workspaces/{ws_id}/records", tags=["records"])


@router.get("", response_model=PaginatedRecordsResponse)
def query_records(
    ws_id: str,
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(50, ge=1, le=200, description="1ページあたりの件数"),
    filter_status: str = Query("すべて", description="ステータスフィルタ"),
    search_query: str = Query("", description="検索キーワード"),
    stage: Optional[str] = Query(None, description="ステージフィルタ (TYPE, RULE_ABOUT等)"),
    target_type: Optional[str] = Query(None, description="特定リソース型"),
    provider: Optional[str] = Query(None, description="所蔵館・提供元フィルタ"),
    year_from: Optional[int] = Query(None, description="出版年 開始"),
    year_to: Optional[int] = Query(None, description="出版年 終了"),
    has_image: Optional[bool] = Query(None, description="画像有無"),
    creator: Optional[str] = Query(None, description="著者・編者フィルタ"),
    filter_source: Optional[str] = Query(None, description="判定ソースフィルタ")
):
    """
    DuckDB から必要なページ分のみを高速返却するサーバーサイドページネーションAPI
    """
    return record_service.query_records(
        ws_id=ws_id,
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


@router.get("/metrics", response_model=ReviewMetrics)
def get_review_metrics(ws_id: str):
    """査読集約メトリクス（合格・除外・保留・修正数）を取得"""
    return record_service.get_review_metrics(ws_id)


@router.get("/facets", response_model=FacetsResponse)
def get_facets(ws_id: str):
    """所蔵館別・年代別・画像有無のファセット件数分布を取得"""
    return record_service.get_facets(ws_id)


@router.post("/decision")
def update_decision_body(ws_id: str, req: UpdateDecisionRequest):
    """
    専門家による合否判定をJSONボディで受け取り即時更新 (URL安全)
    """
    if not req.record_id:
        raise HTTPException(status_code=400, detail="record_id は必須です。")
    success = record_service.update_decision(ws_id, req.record_id, req.human_decision)
    if not success:
        raise HTTPException(status_code=400, detail="判定の更新に失敗しました。")
    return {"message": "判定を正常に更新しました。", "id": req.record_id, "decision": req.human_decision}


@router.patch("/{record_id:path}/decision")
def update_decision(ws_id: str, record_id: str, req: UpdateDecisionRequest):
    """
    専門家による合否判定（合格 / 除外 / None）を手動オーバーライド更新
    DuckDBを即時更新し、確定JSONLへ即時オートセーブ同期
    """
    target_id = req.record_id or record_id
    success = record_service.update_decision(ws_id, target_id, req.human_decision)
    if not success:
        raise HTTPException(status_code=400, detail="判定の更新に失敗しました。")
    return {"message": "判定を正常に更新しました。", "id": target_id, "decision": req.human_decision}


@router.post("/export-verified")
def export_verified(ws_id: str):
    """確定査読データセット (human_verified_cleaned.jsonl) を手動同期エクスポート"""
    cnt = record_service.export_verified(ws_id)
    return {"message": f"{cnt:,} 件の確定データをエクスポートしました。", "count": cnt}
