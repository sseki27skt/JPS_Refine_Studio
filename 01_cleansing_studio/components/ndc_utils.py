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

# ローカル永続キャッシュファイルのパス（プロジェクトルートまたはスタジオディレクトリから安全に解決）
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_STUDIO_DIR = os.path.dirname(_CURRENT_DIR)
_ROOT_DIR = os.path.dirname(_STUDIO_DIR) if os.path.basename(_STUDIO_DIR) == "01_cleansing_studio" else _STUDIO_DIR

CACHE_DIR = os.path.join(_ROOT_DIR, "data")
if not os.path.exists(CACHE_DIR):
    # フォールバックとして studio/data またはカレントの data
    CACHE_DIR = os.path.join(_STUDIO_DIR, "data") if os.path.exists(os.path.join(_STUDIO_DIR, "data")) else os.path.join(_ROOT_DIR, "data")

NDC_CACHE_FILE = os.path.join(CACHE_DIR, "ndc_api_cache.json")
NDLNA_CACHE_FILE = os.path.join(CACHE_DIR, "ndlna_api_cache.json")
NDLC_CACHE_FILE = os.path.join(CACHE_DIR, "ndlc_api_cache.json")

_mem_ndc_cache = {}
_mem_ndlna_cache = {}
_mem_ndlc_cache = {}
_ndc_cache_dirty = False
_ndlna_cache_dirty = False
_ndlc_cache_dirty = False

# 正規表現パターン
_NDC_REGEX = re.compile(r'^(?:ndc(?:[0-9]|10)?[\s:#/_]*)?([0-9]{1,3}(?:\.[0-9]+)?)$', re.IGNORECASE)
_NDL_AUTH_REGEX = re.compile(
    r'^(?:https?://id\.ndl\.go\.jp/auth/(ndlsh|ndlna)/|(ndlsh|ndlna|ndla)[:#/_]*\s*)?(0[0-9]{6,8})$',
    re.IGNORECASE
)
_NDLNA_REGEX = _NDL_AUTH_REGEX  # 後方互換性のためエイリアス維持
_NDLC_REGEX = re.compile(
    r'^(?:https?://id\.ndl\.go\.jp/class/ndlc/|ndlc[\s:#/_]+)?([A-Z]{1,2}[0-9]{1,4}(?:-[0-9A-Z]+)?)$',
    re.IGNORECASE
)

# 解決ラベルのローカルメモ化
_resolved_ndc_memo = {}
_resolved_ndlna_memo = {}
_resolved_ndlc_memo = {}


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


def extract_ndl_auth_info(text: str) -> tuple:
    """
    文字列から NDL 典拠情報（auth_id, auth_type）を抽出。
    例:
      - 'http://id.ndl.go.jp/auth/ndlsh/00573385' -> ('00573385', 'ndlsh')
      - 'ndlna:00054222' -> ('00054222', 'ndlna')
      - '00450717' -> ('00450717', 'unknown')
    """
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    m = _NDL_AUTH_REGEX.match(s)
    if m:
        t1, t2, auth_id = m.groups()
        auth_type = (t1 or t2 or "unknown").lower()
        if auth_type == "ndla":
            auth_type = "unknown"
        return (auth_id, auth_type)
    return None


def extract_ndlna_id(text: str) -> str:
    """文字列から NDL 典拠ID（例: '00450717'）を抽出（後方互換用）"""
    info = extract_ndl_auth_info(text)
    return info[0] if info else None


def fetch_ndl_authorities_sparql_batch(auth_items: list, timeout: float = 3.0) -> dict:
    """
    SPARQL 1.1 エンドポイント (Virtuoso) を使用し、複数の典拠ID (NDLSH / NDLNA) の
    ラベル（標目名）および読みを1クエリで一括高速取得（Bulk Fetch）してキャッシュします。
    """
    global _mem_ndlna_cache, _ndlna_cache_dirty
    if not auth_items:
        return {}

    _load_ndlna_cache()

    # 未キャッシュのIDとURIリストを構築
    uris_to_fetch = set()
    id_map = {}  # uri -> auth_id
    aids_to_fetch = set()

    for item in auth_items:
        if isinstance(item, tuple):
            aid, atype = item
        else:
            aid = str(item).strip()
            atype = "unknown"

        if not aid:
            continue
        if aid in _mem_ndlna_cache:
            continue

        aids_to_fetch.add(aid)
        if atype == "ndlsh":
            u = f"http://id.ndl.go.jp/auth/ndlsh/{aid}"
            uris_to_fetch.add(u)
            id_map[u] = aid
        elif atype == "ndlna":
            u = f"http://id.ndl.go.jp/auth/ndlna/{aid}"
            uris_to_fetch.add(u)
            id_map[u] = aid
        else:
            # タイプ不明の場合は件名・名称の両方を問い合わせ対象にする
            u_sh = f"http://id.ndl.go.jp/auth/ndlsh/{aid}"
            u_na = f"http://id.ndl.go.jp/auth/ndlna/{aid}"
            uris_to_fetch.add(u_sh)
            uris_to_fetch.add(u_na)
            id_map[u_sh] = aid
            id_map[u_na] = aid

    if not uris_to_fetch:
        return _mem_ndlna_cache

    # 1クエリあたり最大100件ずつ分割して実行
    uri_list = list(uris_to_fetch)
    chunk_size = 100

    for i in range(0, len(uri_list), chunk_size):
        chunk = uri_list[i:i + chunk_size]
        values_clause = " ".join([f"<{u}>" for u in chunk])
        
        sparql_query = f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
PREFIX ndl: <http://ndl.go.jp/dcndl/terms/>

SELECT ?uri ?label ?yomi WHERE {{
  VALUES ?uri {{ {values_clause} }}
  OPTIONAL {{ ?uri rdfs:label ?label }}
  OPTIONAL {{
    ?uri xl:prefLabel [ ndl:transcription ?yomi ] .
    FILTER (lang(?yomi) = 'ja-kana' || lang(?yomi) = 'ja-Kana' || lang(?yomi) = 'ja-latn')
  }}
}}
"""
        endpoint = "https://id.ndl.go.jp/auth/ndla/sparql"
        try:
            res = requests.get(
                endpoint,
                params={"query": sparql_query, "format": "json"},
                headers={"Accept": "application/json"},
                timeout=timeout
            )
            if res.status_code == 200:
                data = res.json()
                bindings = data.get("results", {}).get("bindings", [])

                for b in bindings:
                    u_val = b.get("uri", {}).get("value", "")
                    lbl = b.get("label", {}).get("value", "")
                    # labelのないバインディング（別グラフでの不一致など）はスキップ
                    if not u_val or not lbl:
                        continue
                    
                    aid = id_map.get(u_val) or u_val.split("/")[-1]
                    yomi = b.get("yomi", {}).get("value", "")
                    atype = "ndlsh" if "/ndlsh/" in u_val else "ndlna"

                    existing = _mem_ndlna_cache.get(aid, {})
                    cur_lbl = existing.get("label") or lbl
                    cur_yomi = existing.get("yomi") or yomi
                    
                    _mem_ndlna_cache[aid] = {
                        "status": 200,
                        "label": cur_lbl,
                        "prefLabel": cur_lbl,
                        "yomi": cur_yomi,
                        "type": atype,
                        "uri": u_val
                    }
                    _ndlna_cache_dirty = True
        except Exception:
            pass

    # 全クエリ終了後、どのURIでもマッチしなかったIDのみ404として記録
    for aid in aids_to_fetch:
        if aid not in _mem_ndlna_cache:
            _mem_ndlna_cache[aid] = {
                "status": 404,
                "label": "",
                "prefLabel": "",
                "yomi": "",
                "type": "unknown"
            }
            _ndlna_cache_dirty = True

    save_ndlna_cache()
    return _mem_ndlna_cache


def fetch_ndlna_from_api(auth_id: str, save_immediate: bool = False, allow_network: bool = False) -> dict:
    """単一IDの解決（キャッシュ優先、必要ならSPARQL一括取得関数を委譲呼び出し）"""
    global _mem_ndlna_cache
    if not auth_id:
        return None
    _load_ndlna_cache()
    if auth_id in _mem_ndlna_cache:
        return _mem_ndlna_cache[auth_id]

    if not allow_network:
        return None

    # SPARQL一括APIを単一IDで呼び出す
    fetch_ndl_authorities_sparql_batch([auth_id])
    return _mem_ndlna_cache.get(auth_id)


def resolve_ndlna_label(auth_id: str, allow_network: bool = False) -> str:
    """NDL 典拠ID（NDLNA / NDLSH）から日本語・代表ラベルを取得"""
    if not auth_id:
        return ""
    if auth_id in _resolved_ndlna_memo:
        return _resolved_ndlna_memo[auth_id]

    _load_ndlna_cache()
    info = _mem_ndlna_cache.get(auth_id)
    if not info and allow_network:
        # キャッシュにない場合、即座にSPARQLで単一フェッチを試みる
        fetch_ndl_authorities_sparql_batch([auth_id], timeout=2.0)
        info = _mem_ndlna_cache.get(auth_id)

    if info and info.get("status") == 200:
        lbl = info.get("prefLabel") or info.get("label", "")
        if lbl:
            _resolved_ndlna_memo[auth_id] = lbl
            return lbl

    _resolved_ndlna_memo[auth_id] = ""
    return ""


# =============================================================================
# NDLC (国立国会図書館分類表) キャッシュ ＆ 解決
# =============================================================================

def _load_ndlc_cache():
    global _mem_ndlc_cache
    if not _mem_ndlc_cache and os.path.exists(NDLC_CACHE_FILE):
        try:
            with open(NDLC_CACHE_FILE, "r", encoding="utf-8") as f:
                _mem_ndlc_cache = json.load(f)
        except Exception:
            _mem_ndlc_cache = {}


def save_ndlc_cache(force: bool = False):
    global _mem_ndlc_cache, _ndlc_cache_dirty
    if not force and not _ndlc_cache_dirty:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = NDLC_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_mem_ndlc_cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NDLC_CACHE_FILE)
        _ndlc_cache_dirty = False
    except Exception:
        pass


def extract_ndlc_code(text: str) -> str:
    """
    文字列から NDLC（国立国会図書館分類表）コードを抽出。
    例:
      - 'http://id.ndl.go.jp/class/ndlc/KD461' -> 'KD461'
      - 'ndlc:KD461' -> 'KD461'
      - 'KD461' -> 'KD461'
    """
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    m = _NDLC_REGEX.match(s)
    if m:
        return m.group(1).upper()
    return None


def fetch_ndlc_sparql_batch(ndlc_codes: list, timeout: float = 3.0) -> dict:
    """
    SPARQL 1.1 エンドポイントを使用し、複数の NDLC 分類記号に紐付く
    代表普通件名（Topical Terms）のラベルを1クエリで一括高速取得してキャッシュします。
    """
    global _mem_ndlc_cache, _ndlc_cache_dirty
    if not ndlc_codes:
        return {}

    _load_ndlc_cache()

    codes_to_fetch = set()
    for item in ndlc_codes:
        if not item:
            continue
        c = extract_ndlc_code(item) if isinstance(item, str) else None
        if c and c not in _mem_ndlc_cache:
            codes_to_fetch.add(c)

    if not codes_to_fetch:
        return _mem_ndlc_cache

    code_list = list(codes_to_fetch)
    chunk_size = 100

    for i in range(0, len(code_list), chunk_size):
        chunk = code_list[i:i + chunk_size]
        values_clause = " ".join([f"<http://id.ndl.go.jp/class/ndlc/{c}>" for c in chunk])

        sparql_query = f"""PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?ndlc ?label WHERE {{
  VALUES ?ndlc {{ {values_clause} }}
  ?subj skos:relatedMatch ?ndlc ;
        skos:inScheme <http://id.ndl.go.jp/auth#topicalTerms> ;
        rdfs:label ?label .
}}
"""
        endpoint = "https://id.ndl.go.jp/auth/ndla/sparql"
        try:
            res = requests.get(
                endpoint,
                params={"query": sparql_query, "format": "json"},
                headers={"Accept": "application/json"},
                timeout=timeout
            )
            if res.status_code == 200:
                data = res.json()
                bindings = data.get("results", {}).get("bindings", [])

                fetched_labels = {}
                for b in bindings:
                    ndlc_uri = b.get("ndlc", {}).get("value", "")
                    lbl = b.get("label", {}).get("value", "")
                    if not ndlc_uri or not lbl:
                        continue
                    c = ndlc_uri.split("/")[-1].upper()
                    if c not in fetched_labels:
                        fetched_labels[c] = []
                    if lbl not in fetched_labels[c]:
                        fetched_labels[c].append(lbl)

                for c in chunk:
                    lbls = fetched_labels.get(c, [])
                    disp = ", ".join(lbls[:3])
                    _mem_ndlc_cache[c] = {
                        "status": 200 if lbls else 404,
                        "code": c,
                        "uri": f"http://id.ndl.go.jp/class/ndlc/{c}",
                        "labels": lbls,
                        "display_label": disp
                    }
                    _ndlc_cache_dirty = True
        except Exception:
            pass

    for c in codes_to_fetch:
        if c not in _mem_ndlc_cache:
            _mem_ndlc_cache[c] = {
                "status": 404,
                "code": c,
                "uri": f"http://id.ndl.go.jp/class/ndlc/{c}",
                "labels": [],
                "display_label": ""
            }
            _ndlc_cache_dirty = True

    save_ndlc_cache()
    return _mem_ndlc_cache


def resolve_ndlc_label(code: str, allow_network: bool = False) -> str:
    """NDLC 分類記号から代表普通件名ラベル（例: '謡曲, 謡本'）を取得"""
    c = extract_ndlc_code(code)
    if not c:
        return ""
    if c in _resolved_ndlc_memo:
        return _resolved_ndlc_memo[c]

    _load_ndlc_cache()
    info = _mem_ndlc_cache.get(c)
    if not info and allow_network:
        fetch_ndlc_sparql_batch([c], timeout=2.0)
        info = _mem_ndlc_cache.get(c)

    if info and info.get("status") == 200:
        lbl = info.get("display_label") or (", ".join(info.get("labels", [])[:3]))
        if lbl:
            _resolved_ndlc_memo[c] = lbl
            return lbl

    _resolved_ndlc_memo[c] = ""
    return ""


def make_ndlc_url(code: str) -> str:
    """NDLC 分類記号の公式検索URLを生成"""
    c = extract_ndlc_code(code)
    if not c:
        return ""
    return f"https://id.ndl.go.jp/class/ndlc/{c}"


# =============================================================================
# 一括バッチ事前解決 ＆ キャッシュ永続化
# =============================================================================

def prefetch_about_keywords_batch(keywords: list, max_workers: int = 8, max_items: int = 150):
    """
    キーワードリストから未解決の NDC / NDLNA / NDLSH を抽出し、
    NDCは並列API、NDL典拠はSPARQL 1.1の一括クエリ（1発）で高速取得・キャッシュ化。
    画面描画時のフリーズをゼロにします。
    """
    if not keywords:
        return

    _load_ndc_cache()
    _load_ndlna_cache()

    ndc_to_fetch = set()
    ndl_to_fetch = set()
    ndlc_to_fetch = set()

    for kw in keywords[:max_items]:
        if not kw:
            continue
        
        # 1. NDC
        ndc_num = extract_ndc_number(kw)
        if ndc_num:
            if ndc_num not in _mem_ndc_cache:
                ndc_to_fetch.add(ndc_num)
            if "." in ndc_num:
                base = ndc_num.split(".")[0]
                if base not in _mem_ndc_cache:
                    ndc_to_fetch.add(base)
            elif len(ndc_num) == 3:
                b2 = ndc_num[:2] + "0"
                if b2 not in _mem_ndc_cache:
                    ndc_to_fetch.add(b2)
            continue
        
        # 2. NDL 典拠 (NDLSH / NDLNA)
        auth_info = extract_ndl_auth_info(kw)
        if auth_info:
            aid, atype = auth_info
            if aid not in _mem_ndlna_cache:
                ndl_to_fetch.add((aid, atype))
            continue

        # 3. NDLC
        ndlc_code = extract_ndlc_code(kw)
        if ndlc_code:
            if ndlc_code not in _mem_ndlc_cache:
                ndlc_to_fetch.add(ndlc_code)

    # NDL 典拠の一括取得 (SPARQL 1クエリ)
    if ndl_to_fetch:
        fetch_ndl_authorities_sparql_batch(list(ndl_to_fetch))

    # NDLC の一括取得 (SPARQL 1クエリ)
    if ndlc_to_fetch:
        fetch_ndlc_sparql_batch(list(ndlc_to_fetch))

    # NDC の並列取得
    if ndc_to_fetch:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for ndc in ndc_to_fetch:
                executor.submit(fetch_ndc_from_api, ndc, False, True)

    save_all_caches()


def save_all_caches():
    """NDC, NDLNA, NDLC のメモリキャッシュをディスクに保存"""
    save_ndc_cache()
    save_ndlna_cache()
    save_ndlc_cache()


# =============================================================================
# 統合フォーマッタ ＆ リンク生成
# =============================================================================

def format_about_keyword_display(kw: str, max_label_len: int = 30, allow_network: bool = False) -> str:
    """
    Aboutキーワードの表示用フォーマット。
    NDC / NDLSH / NDLNA を自動判別し、人間がパッと理解できる日本語ラベルを主役に整形します。
    例:
      - '00573385' -> '図書館 [00573385]'
      - 'ndlsh:00573385' -> '図書館 [ndlsh:00573385]'
      - 'ndlna:00054222' -> '夏目, 漱石, 1867-1916 [ndlna:00054222]'
    """
    if not kw:
        return ""
    
    # 1. NDC の判定
    ndc_num = extract_ndc_number(kw)
    if ndc_num:
        m_pref = re.match(r'^(ndc(?:[0-9]|10)?[\s:#/_]+)', kw.strip(), re.I)
        prefix_tag = f" ({m_pref.group(1).rstrip(' ')}表記)" if m_pref else ""

        label, is_exact, parent_code = resolve_ndc_label(ndc_num)
        if label:
            disp_lbl = label if len(label) <= max_label_len else label[:max_label_len] + "..."
            if is_exact:
                return f"{ndc_num} [{disp_lbl}]{prefix_tag}"
            else:
                return f"{ndc_num} [上位: {parent_code} {disp_lbl}]{prefix_tag}"
        return f"{ndc_num} [NDC分類]{prefix_tag}"

    # 2. NDL 典拠 (NDLSH / NDLNA) の判定
    auth_info = extract_ndl_auth_info(kw)
    if auth_info:
        auth_id, auth_type = auth_info
        auth_lbl = resolve_ndlna_label(auth_id, allow_network=allow_network)
        
        orig_s = kw.strip()
        # 元がプレフィックス付きならそれを維持したタグにする
        if "ndlsh" in orig_s.lower():
            tag = f"ndlsh:{auth_id}"
        elif "ndlna" in orig_s.lower():
            tag = f"ndlna:{auth_id}"
        else:
            tag = auth_id

        if auth_lbl:
            disp_auth = auth_lbl if len(auth_lbl) <= max_label_len else auth_lbl[:max_label_len] + "..."
            # 日本語ラベルを主役に表示！
            return f"{disp_auth} [{tag}]"
        return tag

    # 3. NDLC の判定
    ndlc_code = extract_ndlc_code(kw)
    if ndlc_code:
        ndlc_lbl = resolve_ndlc_label(ndlc_code, allow_network=allow_network)
        orig_s = kw.strip()
        tag = f"ndlc:{ndlc_code}" if "ndlc" in orig_s.lower() else ndlc_code

        if ndlc_lbl:
            disp_lbl = ndlc_lbl if len(ndlc_lbl) <= max_label_len else ndlc_lbl[:max_label_len] + "..."
            return f"{disp_lbl} [{tag}]"
        return f"{tag} [NDLC分類]"

    return kw


def make_ndc_navi_url(ndc_num: str, edition: int = 9) -> str:
    if not ndc_num:
        return ""
    q = urllib.parse.quote(ndc_num)
    if edition == 10:
        return f"https://ndcnavi.i.omu.ac.jp/#/?class={q}"
    return f"https://ndcnavi.i.omu.ac.jp/ndcnavi9/?class={q}"


def make_ndl_auth_url(auth_id: str, auth_type: str = None) -> str:
    """Web NDL Authorities の公式典拠URLを生成（件名・名称を適切に振り分け）"""
    if not auth_id:
        return ""
    if not auth_type or auth_type == "unknown":
        _load_ndlna_cache()
        cached = _mem_ndlna_cache.get(auth_id, {})
        auth_type = cached.get("type", "ndlna")
    
    endpoint_type = "ndlsh" if auth_type == "ndlsh" else "ndlna"
    return f"https://id.ndl.go.jp/auth/{endpoint_type}/{auth_id}"


def make_ndlna_url(auth_id: str) -> str:
    """後方互換用エイリアス"""
    return make_ndl_auth_url(auth_id)
