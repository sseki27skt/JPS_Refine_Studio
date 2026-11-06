# -*- coding: utf-8 -*-
"""
ワークスペース・スナップショット・ダッシュボード API
"""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

from ..schemas.workspace import (
    WorkspaceMeta, WorkspaceCreateRequest, DashboardStats,
    SnapshotCreateRequest, SnapshotMeta
)
from ..services.workspace_service import workspace_service

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("", response_model=List[WorkspaceMeta])
def list_workspaces():
    """全ワークスペース一覧を取得"""
    return workspace_service.list_workspaces()


@router.post("", response_model=WorkspaceMeta)
def create_workspace(req: WorkspaceCreateRequest):
    """新規ワークスペースを作成（クローン対応）"""
    try:
        return workspace_service.create_workspace(
            ws_id=req.id,
            name=req.name,
            description=req.description or "",
            research_theme=req.research_theme or "",
            clone_from=req.clone_from
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ワークスペース作成エラー: {e}")


@router.get("/{ws_id}", response_model=WorkspaceMeta)
def get_workspace(ws_id: str):
    """特定ワークスペースの詳細情報を取得"""
    w = workspace_service.get_workspace(ws_id)
    if not w:
        raise HTTPException(status_code=404, detail="指定されたワークスペースが見つかりません。")
    return w


@router.delete("/{ws_id}")
def delete_workspace(ws_id: str):
    """ワークスペースを削除"""
    success = workspace_service.delete_workspace(ws_id)
    if not success:
        raise HTTPException(status_code=404, detail="指定されたワークスペースが見つかりません。")
    return {"message": f"ワークスペース '{ws_id}' を削除しました。"}


@router.get("/{ws_id}/dashboard", response_model=DashboardStats)
def get_dashboard_stats(ws_id: str):
    """ダッシュボード用集計メトリクス（PRISMAフロー件数）を取得"""
    return workspace_service.get_dashboard_stats(ws_id)


# スナップショット関連
@router.get("/{ws_id}/snapshots", response_model=List[SnapshotMeta])
def list_snapshots(ws_id: str):
    """スナップショット一覧を取得"""
    return workspace_service.list_snapshots(ws_id)


@router.post("/{ws_id}/snapshots", response_model=SnapshotMeta)
def create_snapshot(ws_id: str, req: SnapshotCreateRequest):
    """現在のルールおよび判定ステータスをスナップショット保存"""
    return workspace_service.create_snapshot(ws_id, req.name, req.description or "")


@router.post("/{ws_id}/snapshots/{snap_id}/restore")
def restore_snapshot(ws_id: str, snap_id: str):
    """スナップショットから状態を復元"""
    try:
        res = workspace_service.restore_snapshot(ws_id, snap_id)
        return {"message": "スナップショットを正常に復元しました。", "details": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"スナップショット復元エラー: {e}")

