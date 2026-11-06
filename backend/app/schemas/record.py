# -*- coding: utf-8 -*-
"""
レコード・査読ポータル関連の Pydantic スキーマ
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class RecordItem(BaseModel):
    id: str
    title: str
    description: str = ""
    about_list: List[str] = []
    type_list: List[str] = []
    provider: Optional[str] = ""
    published_year: Optional[int] = None
    has_image: bool = False
    creator: Optional[str] = ""
    final_decision: str = "GREY"
    status: str = "除外"
    cur_status: str = "除外"
    human_decision: Optional[str] = None
    is_override: bool = False
    is_conflict: bool = False
    matched_reason: Optional[str] = ""
    primary_reason: Optional[str] = ""
    reasons: Optional[str] = ""
    type_status: Optional[str] = None
    type_reason: Optional[str] = None
    about_status: Optional[str] = None
    about_reason: Optional[str] = None
    ngram_status: Optional[str] = None
    ngram_reason: Optional[str] = None
    llm_status: Optional[str] = None
    llm_target: Optional[bool] = None
    llm_reason: Optional[str] = ""
    external_info: Optional[str] = ""
    raw_item: Optional[Dict[str, Any]] = None


class PaginatedRecordsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    records: List[RecordItem]


class ReviewMetrics(BaseModel):
    total: int = 0
    passed_cnt: int = 0
    reject_cnt: int = 0
    override_cnt: int = 0
    null_cnt: int = 0


class FacetItem(BaseModel):
    name: str
    count: int


class EraDistributionItem(BaseModel):
    era: str
    count: int


class FacetsResponse(BaseModel):
    top_providers: List[FacetItem] = []
    era_distribution: List[EraDistributionItem] = []
    has_image_count: int = 0
    no_image_count: int = 0


class UpdateDecisionRequest(BaseModel):
    record_id: Optional[str] = None
    human_decision: Optional[str] = None  # "合格" | "除外" | None
