# -*- coding: utf-8 -*-
"""
Web NDL Authorities SPARQL 解決 API
"""
from typing import List
from pydantic import BaseModel
from fastapi import APIRouter

from ..services.ndc_service import ndc_service

router = APIRouter(prefix="/api/ndc", tags=["ndc"])


class ResolveNdcRequest(BaseModel):
    ndc_numbers: List[str]


class ResolveAuthRequest(BaseModel):
    auth_ids: List[str]


@router.post("/resolve-batch")
def resolve_ndc_batch(req: ResolveNdcRequest):
    """Web NDL Authorities SPARQL による NDC 一括解決"""
    return ndc_service.resolve_ndc_batch(req.ndc_numbers)


@router.post("/resolve-auth-batch")
def resolve_auth_batch(req: ResolveAuthRequest):
    """Web NDL Authorities SPARQL による NDL 典拠 (NDLNA/NDLSH) 一括解決"""
    return ndc_service.resolve_ndlna_batch(req.auth_ids)

