# -*- coding: utf-8 -*-
"""
フィルタ・クレンジングルール管理および影響レコード完全一覧 API
"""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

from ..schemas.rule import (
    TypeRuleUpdate, KeyValueRulesUpdate, RuleImpactRequest,
    RuleImpactResponse, RuleApplyResponse, ClusterItem
)
from ..services.rule_service import rule_service

router = APIRouter(prefix="/api/workspaces/{ws_id}/rules", tags=["rules"])


# 1. Type ルール
@router.get("/type")
def get_type_rules(ws_id: str):
    """Typeルールおよび種別統計を取得"""
    return rule_service.get_type_rules_and_stats(ws_id)


@router.put("/type")
def save_type_rules(ws_id: str, req: TypeRuleUpdate):
    """Typeルール (NGリスト) を保存"""
    rule_service.save_type_rules(ws_id, req.NG, req.OK)
    return {"message": f"Typeルール ({len(req.NG)} 件) を保存しました。"}


# 2. About ルール & 高度クラスタリング
@router.get("/about")
def get_about_rules(ws_id: str):
    """Aboutルール辞書を取得"""
    return rule_service.get_about_rules(ws_id)


@router.put("/about")
def save_about_rules(ws_id: str, req: KeyValueRulesUpdate):
    """Aboutルール辞書を保存"""
    rule_service.save_about_rules(ws_id, req.rules)
    return {"message": f"Aboutルール ({len(req.rules)} 件) を保存しました。"}


@router.get("/about/clusters", response_model=List[ClusterItem])
def get_about_clusters(ws_id: str):
    """NDC 3段階階層ツリーおよびNDL典拠分離による高度クラスタ一覧を取得"""
    return rule_service.get_about_clusters(ws_id)


# 3. N-gram ルール & 接尾辞クラスタリング
@router.get("/ngram")
def get_ngram_rules(ws_id: str):
    """N-gramルール辞書を取得"""
    return rule_service.get_ngram_rules(ws_id)


@router.put("/ngram")
def save_ngram_rules(ws_id: str, req: KeyValueRulesUpdate):
    """N-gramルール辞書を保存"""
    rule_service.save_ngram_rules(ws_id, req.rules)
    return {"message": f"N-gramルール ({len(req.rules)} 件) を保存しました。"}


@router.get("/ngram/rankings")
def get_ngram_rankings(ws_id: str):
    """N-gram出現頻度ランキングおよび接尾辞（〜譜、〜集等）クラスタを取得"""
    return rule_service.get_ngram_rankings_and_clusters(ws_id)


# 4. ★ ルール影響レコード完全一覧 (ページネーション & 衝突警告)
@router.post("/impact-records", response_model=RuleImpactResponse)
def query_impact_records(ws_id: str, req: RuleImpactRequest):
    """
    指定ルールが影響を与える全レコードを取得（上限打ち切りなしの完全一覧）。
    すでに確定OKとなっている重要資料が紛れていないかを判定する衝突警告件数も返却。
    """
    return rule_service.query_impact_records(
        ws_id=ws_id,
        rule_type=req.rule_type,
        rule_value=req.rule_value,
        rule_action=req.rule_action,
        page=req.page,
        page_size=req.page_size,
        search_query=req.search_query or "",
        warning_only=req.warning_only
    )


# 5. ルール一括適用ジョブ
@router.post("/apply", response_model=RuleApplyResponse)
def apply_rules(ws_id: str):
    """ルール一括適用ジョブを非同期バックグラウンドで開始"""
    return rule_service.start_apply_rules_job(ws_id)

