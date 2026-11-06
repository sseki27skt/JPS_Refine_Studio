# -*- coding: utf-8 -*-
"""
フィルタ・クレンジングルールおよび影響レコード完全一覧関連の Pydantic スキーマ
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from .record import RecordItem


class TypeRuleUpdate(BaseModel):
    NG: List[str] = []
    OK: List[str] = []


class KeyValueRulesUpdate(BaseModel):
    rules: Dict[str, str]  # {"キーワード": "OK" | "NG"}


class RuleImpactRequest(BaseModel):
    rule_type: str  # "type" | "about" | "ngram"
    rule_value: str  # 例: "768", "画譜", "記事・論文"
    rule_action: str = "NG"  # "NG" | "OK"
    page: int = 1
    page_size: int = 50
    search_query: Optional[str] = ""
    warning_only: bool = False  # すでに確定合格している巻き添えレコードのみ抽出


class RuleImpactResponse(BaseModel):
    total_impact_count: int
    warning_conflict_count: int  # 巻き添えになる確定OK/手動合格の件数
    page: int
    page_size: int
    total_pages: int
    records: List[RecordItem]


class RuleApplyResponse(BaseModel):
    job_id: str
    message: str


# クラスタリング関連
class ClusterItem(BaseModel):
    cluster_id: str
    name: str
    category: str = "general"  # "ndc_tree" | "ndlna_person" | "ndlsh_topic" | "ngram_suffix" | "general"
    keywords: List[str]
    total_count: int
    resolved_label: Optional[str] = None
    sub_clusters: Optional[List[Dict[str, Any]]] = None

