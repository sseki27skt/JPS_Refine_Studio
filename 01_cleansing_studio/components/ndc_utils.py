# -*- coding: utf-8 -*-
"""
JS-Refine Studio - NDC ＆ Web NDL Authorities (NDLNA) API 連携 ＆ 超高速ローカルキャッシュ解決ユーティリティ
- NDC 公式 API: https://api-4pccg7v5ma-an.a.run.app/ndc9/{notation}
- NDLNA 公式 API: https://id.ndl.go.jp/auth/ndlna/{auth_id}
"""

import json
import os
import re
import urllib.parse
import requests
from concurrent.futures import ThreadPoolExecutor

# ローカル永続キャッシュファイルのパス
CACHE_DIR = "data"
NDC_CACHE_FILE = os.path.join(CACHE_DIR, "ndc_api_cache.json")
NDLNA_CACHE_FILE = os.path.join(CACHE_DIR, "ndlna_api_cache.json")

_mem_ndc_cache = {}
_mem_ndlna_cache = {}
_ndc_cache_dirty = False
_ndlna_cache_dirty = False

# 正規表現パターン
_NDC_REGEX = re.compile(r'^(?:ndc(?:[0-9]|10)?[\s:#/_]*)?([0-9]{1,3}(?:\.[0-9]+)?)$', re.IGNORECASE)
_NDLNA_REGEX = re.compile(r'^(?:https?://id\.ndl\.go\.jp/auth/ndlna/|ndlna[:#/_]*)?(0[0-9]{6,8})$', re.IGNORECASE)

# 解決ラベルのローカルメモ化
_resolved_ndc_memo = {}
_resolved_ndlna_memo = {}


# =============================================================================
# NDC キャッシュ ＆ 解決
# =============================================================================

def _load_ndc_cache():
    global _mem_ndc_cache
    if not _mem_ndc_cache and os.path.exists(NDC_CACHE_FILE):
        try:
            with open(NDC_CACHE_FILE, "r", encoding="utf-8") as f:
                _mem_ndc_cache = json.load(f)
        except Exception:
            _mem_ndc_cache = {}


def save_ndc_cache(force: bool = False):
    global _mem_ndc_cache, _ndc_cache_dirty
    if not force and not _ndc_cache_dirty:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = NDC_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_mem_ndc_cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NDC_CACHE_FILE)
        _ndc_cache_dirty = False
    except Exception:
        pass


def fetch_ndc_from_api(ndc_num: str, save_immediate: bool = False, allow_network: bool = False) -> dict:
    global _mem_ndc_cache, _ndc_cache_dirty
    if not ndc_num:
        return None
    _load_ndc_cache()
    if ndc_num in _mem_ndc_cache:
        return _mem_ndc_cache[ndc_num]

    if not allow_network:
        return None

    # 1〜2桁の場合は3桁形式（例: 76 -> 760）もAPIキーとして試行
    fetch_key = ndc_num
    if len(ndc_num) == 1:
        fetch_key = ndc_num + "00"
    elif len(ndc_num) == 2:
        fetch_key = ndc_num + "0"

    url = f"https://api-4pccg7v5ma-an.a.run.app/ndc9/{fetch_key}"
    try:
        res = requests.get(url, headers={"accept": "application/json"}, timeout=1.0)
        if res.status_code == 200:
            data = res.json()
            info = {
                "status": 200,
                "label": data.get("label@ja", ""),
                "prefLabel": data.get("prefLabel@ja", ""),
                "broader": data.get("broader", "")
            }
            _mem_ndc_cache[ndc_num] = info
            _ndc_cache_dirty = True
            if save_immediate:
                save_ndc_cache()
            return info
        else:
            info = {"status": res.status_code, "label": "", "prefLabel": "", "broader": ""}
            _mem_ndc_cache[ndc_num] = info
            _ndc_cache_dirty = True
            if save_immediate:
                save_ndc_cache()
            return info
    except Exception:
        info = {"status": 500, "label": "", "prefLabel": "", "broader": ""}
        _mem_ndc_cache[ndc_num] = info
        _ndc_cache_dirty = True
        return info


def extract_ndc_number(text: str) -> str:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    m = _NDC_REGEX.match(s)
    if m:
        return m.group(1)
    if re.match(r'^[0-9]{1,3}(?:\.[0-9]+)?$', s):
        return s
    return None


def resolve_ndc_label(ndc_num: str) -> tuple:
    if not ndc_num:
        return ("", False, "")
    
    if ndc_num in _resolved_ndc_memo:
        return _resolved_ndc_memo[ndc_num]

    info = fetch_ndc_from_api(ndc_num, allow_network=False)
    if info and info.get("status") == 200:
        lbl = info.get("prefLabel") or info.get("label", "")
        res = (lbl, True, ndc_num)
        _resolved_ndc_memo[ndc_num] = res
        return res
    
    parts = ndc_num.split(".")
    if len(parts) == 2:
        base = parts[0]
        decimals = parts[1]
        for l in range(len(decimals) - 1, 0, -1):
            sub_ndc = f"{base}.{decimals[:l]}"
            p_info = fetch_ndc_from_api(sub_ndc)
            if p_info and p_info.get("status") == 200:
                p_lbl = p_info.get("prefLabel") or p_info.get("label", "")
                res = (p_lbl, False, sub_ndc)
                _resolved_ndc_memo[ndc_num] = res
                return res
        
        base_info = fetch_ndc_from_api(base)
        if base_info and base_info.get("status") == 200:
            b_lbl = base_info.get("prefLabel") or base_info.get("label", "")
            res = (b_lbl, False, base)
            _resolved_ndc_memo[ndc_num] = res
            return res
    
    if len(ndc_num) == 3:
        base2 = ndc_num[:2] + "0"
        b2_info = fetch_ndc_from_api(base2)
        if b2_info and b2_info.get("status") == 200:
            res = (b2_info.get("prefLabel") or b2_info.get("label", ""), False, base2)
            _resolved_ndc_memo[ndc_num] = res
            return res
        base1 = ndc_num[:1] + "00"
        b1_info = fetch_ndc_from_api(base1)
        if b1_info and b1_info.get("status") == 200:
            res = (b1_info.get("prefLabel") or b1_info.get("label", ""), False, base1)
            _resolved_ndc_memo[ndc_num] = res
            return res

    res = ("", False, "")
    _resolved_ndc_memo[ndc_num] = res
    return res


# =============================================================================
# Web NDL Authorities (NDLNA) キャッシュ ＆ 解決
# =============================================================================

def _load_ndlna_cache():
    global _mem_ndlna_cache
    if not _mem_ndlna_cache and os.path.exists(NDLNA_CACHE_FILE):
        try:
            with open(NDLNA_CACHE_FILE, "r", encoding="utf-8") as f:
                _mem_ndlna_cache = json.load(f)
        except Exception:
            _mem_ndlna_cache = {}


def save_ndlna_cache(force: bool = False):
    global _mem_ndlna_cache, _ndlna_cache_dirty
    if not force and not _ndlna_cache_dirty:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = NDLNA_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_mem_ndlna_cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NDLNA_CACHE_FILE)
        _ndlna_cache_dirty = False
    except Exception:
        pass


def extract_ndlna_id(text: str) -> str:
    """文字列から NDLNA 典拠ID（例: '00450717'）を抽出"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    m = _NDLNA_REGEX.match(s)
    if m:
        return m.group(1)
    return None


def fetch_ndlna_from_api(auth_id: str, save_immediate: bool = False, allow_network: bool = False) -> dict:
    global _mem_ndlna_cache, _ndlna_cache_dirty
    if not auth_id:
        return None
    _load_ndlna_cache()
    if auth_id in _mem_ndlna_cache:
        return _mem_ndlna_cache[auth_id]

    if not allow_network:
        return None

    url = f"https://id.ndl.go.jp/auth/ndlna/{auth_id}"
    try:
        res = requests.get(url, headers={"Accept": "application/json"}, timeout=1.0)
        if res.status_code == 200:
            data = res.json()
            lbl = data.get("label", "")
            pref = data.get("prefLabel", {})
            pref_lbl = pref.get("literalForm", "") if isinstance(pref, dict) else str(pref)
            
            alt_list = data.get("altLabel", [])
            alt_names = []
            if isinstance(alt_list, list):
                for a in alt_list:
                    if isinstance(a, dict) and "literalForm" in a:
                        alt_names.append(a["literalForm"])
                    elif isinstance(a, str):
                        alt_names.append(a)

            info = {
                "status": 200,
                "label": lbl or pref_lbl,
                "prefLabel": pref_lbl or lbl,
                "altLabel": alt_names[:3]
            }
            _mem_ndlna_cache[auth_id] = info
            _ndlna_cache_dirty = True
            if save_immediate:
                save_ndlna_cache()
            return info
        else:
            info = {"status": res.status_code, "label": "", "prefLabel": "", "altLabel": []}
            _mem_ndlna_cache[auth_id] = info
            _ndlna_cache_dirty = True
            if save_immediate:
                save_ndlna_cache()
            return info
    except Exception:
        info = {"status": 500, "label": "", "prefLabel": "", "altLabel": []}
        _mem_ndlna_cache[auth_id] = info
        _ndlna_cache_dirty = True
        return info


def resolve_ndlna_label(auth_id: str) -> str:
    """NDLNA 典拠IDから日本語・代表ラベルを取得"""
    if not auth_id:
        return ""
    if auth_id in _resolved_ndlna_memo:
        return _resolved_ndlna_memo[auth_id]

    info = fetch_ndlna_from_api(auth_id, allow_network=False)
    if info and info.get("status") == 200:
        lbl = info.get("prefLabel") or info.get("label", "")
        alts = info.get("altLabel", [])
        if alts and alts[0] not in lbl:
            res = f"{lbl} ({alts[0]})"
        else:
            res = lbl
        _resolved_ndlna_memo[auth_id] = res
        return res
    
    _resolved_ndlna_memo[auth_id] = ""
    return ""


# =============================================================================
# 一括バッチ事前解決 ＆ キャッシュ永続化
# =============================================================================

def prefetch_about_keywords_batch(keywords: list, max_workers: int = 8, max_items: int = 30):
    """
    キーワードリストから未解決の NDC / NDLNA を抽出し、並列で一括取得・キャッシュ化。
    画面描画時のフリーズをゼロにします。
    """
    _load_ndc_cache()
    _load_ndlna_cache()

    ndc_to_fetch = set()
    ndlna_to_fetch = set()

    for kw in keywords[:max_items]:
        if not kw:
            continue
        ndc_num = extract_ndc_number(kw)
        if ndc_num:
            if ndc_num not in _mem_ndc_cache:
                ndc_to_fetch.add(ndc_num)
            # 親NDCも事前解決対象に
            if "." in ndc_num:
                base = ndc_num.split(".")[0]
                if base not in _mem_ndc_cache:
                    ndc_to_fetch.add(base)
            elif len(ndc_num) == 3:
                b2 = ndc_num[:2] + "0"
                if b2 not in _mem_ndc_cache:
                    ndc_to_fetch.add(b2)
            continue
        
        auth_id = extract_ndlna_id(kw)
        if auth_id and auth_id not in _mem_ndlna_cache:
            ndlna_to_fetch.add(auth_id)

    if not ndc_to_fetch and not ndlna_to_fetch:
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for ndc in ndc_to_fetch:
            executor.submit(fetch_ndc_from_api, ndc, False)
        for auth in ndlna_to_fetch:
            executor.submit(fetch_ndlna_from_api, auth, False)

    save_all_caches()


def save_all_caches():
    """NDCおよびNDLNAのメモリキャッシュをディスクに保存"""
    save_ndc_cache()
    save_ndlna_cache()


# =============================================================================
# 統合フォーマッタ ＆ リンク生成
# =============================================================================

def format_about_keyword_display(kw: str, max_label_len: int = 30) -> str:
    """Aboutキーワードの表示用フォーマット（NDC / NDLNA を公式APIで自動判別しラベルを付与）"""
    if not kw:
        return ""
    
    # 1. NDC の判定
    ndc_num = extract_ndc_number(kw)
    if ndc_num:
        m_pref = re.match(r'^(ndc(?:[0-9]|10)?[\s:#/_]+)', kw.strip(), re.I)
        prefix_tag = f" ({m_pref.group(1).rstrip(' ')}表記)" if m_pref else ""

        label, is_exact, parent_code = resolve_ndc_label(ndc_num)
        if label:
            if is_exact:
                disp_lbl = label if len(label) <= max_label_len else label[:max_label_len] + "..."
                return f"{ndc_num} [{disp_lbl}]{prefix_tag}"
            else:
                disp_lbl = label if len(label) <= max_label_len else label[:max_label_len] + "..."
                return f"{ndc_num} [上位: {parent_code} {disp_lbl}]{prefix_tag}"
        return f"{ndc_num} [NDC分類]{prefix_tag}"

    # 2. NDLNA / NDLSH（典拠データ）の判定
    auth_id = extract_ndlna_id(kw)
    if auth_id:
        auth_lbl = resolve_ndlna_label(auth_id)
        if auth_lbl:
            disp_auth = auth_lbl if len(auth_lbl) <= max_label_len else auth_lbl[:max_label_len] + "..."
            return f"ndlna:{auth_id} [{disp_auth}]"
        return f"ndlna:{auth_id}"

    return kw


def make_ndc_navi_url(ndc_num: str, edition: int = 9) -> str:
    if not ndc_num:
        return ""
    q = urllib.parse.quote(ndc_num)
    if edition == 10:
        return f"https://ndcnavi.i.omu.ac.jp/#/?class={q}"
    return f"https://ndcnavi.i.omu.ac.jp/ndcnavi9/?class={q}"


def make_ndlna_url(auth_id: str) -> str:
    """Web NDL Authorities の公式典拠URLを生成"""
    if not auth_id:
        return ""
    return f"https://id.ndl.go.jp/auth/ndlna/{auth_id}"
