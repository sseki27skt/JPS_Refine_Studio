# -*- coding: utf-8 -*-
"""
Web NDL Authorities SPARQL NDC/NDLC/NDLNA 解決サービス
"""
from typing import List, Dict, Any
from ..modules.ndc_utils import (
    fetch_ndc_sparql_batch,
    resolve_ndc_label,
    fetch_ndl_authorities_sparql_batch,
    resolve_ndlna_label,
    fetch_ndlc_sparql_batch,
    resolve_ndlc_label
)


class NdcService:
    def resolve_ndc_batch(self, ndc_numbers: List[str]) -> Dict[str, Any]:
        """NDCコードリストを一括解決"""
        fetch_ndc_sparql_batch(ndc_numbers)
        results = {}
        for c in ndc_numbers:
            lbl, is_exact, parent_c = resolve_ndc_label(c)
            results[c] = {
                "label": lbl,
                "is_exact": is_exact,
                "parent_code": parent_c
            }
        return results

    def resolve_ndlna_batch(self, auth_ids: List[str]) -> Dict[str, str]:
        """NDL典拠IDリストを一括解決"""
        fetch_ndl_authorities_sparql_batch(auth_ids)
        return {aid: resolve_ndlna_label(aid) for aid in auth_ids}

    def resolve_ndlc_batch(self, ndlc_codes: List[str]) -> Dict[str, str]:
        """NDLC分類記号リストを一括解決"""
        fetch_ndlc_sparql_batch(ndlc_codes)
        return {code: resolve_ndlc_label(code) for code in ndlc_codes}


ndc_service = NdcService()

