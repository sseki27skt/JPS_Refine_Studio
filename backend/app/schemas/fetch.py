# -*- coding: utf-8 -*-
"""
SPARQL取得・LLM推論関連の Pydantic スキーマ
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class QueryExpandRequest(BaseModel):
    theme: str
    existing_keywords: List[str] = []
    provider: str = "gemini"
    api_key: Optional[str] = None
    model: str = "gemini-3.6-flash"


class QueryExpandResponse(BaseModel):
    keywords: List[str]
    ndc_codes: List[str]
    exclude_ndc_codes: List[str]
    domain_definition: str
    title_regex: str
    desc_regex: str


class StartFetchRequest(BaseModel):
    keywords: List[str]
    ndc_codes: List[str] = []
    exclude_ndc_codes: List[str] = []
    title_regex: Optional[str] = None
    desc_regex: Optional[str] = None
    domain_definition: Optional[str] = None
    batch_size: int = 10
    resume: bool = True


class StartLlmRequest(BaseModel):
    domain_definition: str = "日本の古典籍における楽譜・音楽資料"
    provider: str = "gemini"
    api_base: str = "http://localhost:1234/v1"
    api_key: Optional[str] = ""
    model: str = "gemini-3.6-flash"
    max_workers: int = 2
    limit: Optional[int] = None
    stage2: bool = False  # Stage 2 (判定不能nullに対する再推論) かどうか

