# -*- coding: utf-8 -*-
"""
JS-Refine Studio - ファイル操作 ＆ ヘルパーユーティリティ
"""

import json
import os
import tempfile
import urllib.parse


_line_count_cache = {}

def count_lines(path: str) -> int:
    """指定されたファイルの行数またはJSON要素数を爆速取得（バイナリバッファ＆mtimeキャッシュ）"""
    if not os.path.exists(path):
        return 0
    try:
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        if size == 0:
            return 0
        if path in _line_count_cache and _line_count_cache[path][0] == mtime:
            return _line_count_cache[path][1]

        if path.endswith('.json'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                cnt = len(data) if isinstance(data, list) else 0
        else:
            cnt = 0
            with open(path, 'rb') as f:
                while chunk := f.read(1024 * 1024):
                    cnt += chunk.count(b'\n')
        
        _line_count_cache[path] = (mtime, cnt)
        return cnt
    except Exception:
        return 0


def make_google_link(word: str) -> str:
    """Google検索用のマークダウンリンク文字列を生成"""
    query = urllib.parse.quote(f"{word} とは")
    url = f"https://www.google.com/search?q={query}"
    return f"[🔍 Google]({url})"


def make_jps_keyword_url(keyword: str) -> str:
    """Japan Search の横断キーワード検索URL（csid=jps-cross 必須）を生成"""
    if not keyword:
        return "https://jpsearch.go.jp/csearch/jps-cross?csid=jps-cross"
    q = urllib.parse.quote(str(keyword).strip())
    return f"https://jpsearch.go.jp/csearch/jps-cross?csid=jps-cross&keyword={q}"


def make_jps_about_url(about_kw: str) -> str:
    """Japan Search の主題キーワード検索URL（csid=jps-item & f-about）を生成"""
    if not about_kw:
        return "https://jpsearch.go.jp/csearch/jps-item?csid=jps-item"
    q = urllib.parse.quote(str(about_kw).strip())
    return f"https://jpsearch.go.jp/csearch/jps-item?csid=jps-item&f-about={q}"


def make_jps_item_url(item_id: str, title: str = "") -> str:
    """
    Japan Search の資料詳細URL（またはタイトル検索URL）を生成。
    RDFデータURI（https://jpsearch.go.jp/data/...）をWeb閲覧用詳細ページ（https://jpsearch.go.jp/item/...）に変換します。
    """
    if item_id and str(item_id).startswith("http"):
        s_id = str(item_id).strip()
        if "jpsearch.go.jp/data/" in s_id:
            return s_id.replace("jpsearch.go.jp/data/", "jpsearch.go.jp/item/")
        return s_id
    if title:
        return make_jps_keyword_url(title)
    return "https://jpsearch.go.jp/csearch/jps-cross?csid=jps-cross"


def make_rich_search_links(word: str) -> dict:
    """各種辞書・検索エンジン・ジャパンサーチ・ndc nAVI・NDL AuthoritiesのURL辞書を生成"""
    from components.ndc_utils import (
        extract_ndc_number, make_ndc_navi_url, resolve_ndc_label,
        extract_ndlna_id, make_ndlna_url, resolve_ndlna_label
    )

    q_google = urllib.parse.quote(f"{word} とは")
    q_wiki = urllib.parse.quote(word)
    q_kotobank = urllib.parse.quote(word)

    res = {
        "google": f"https://www.google.com/search?q={q_google}",
        "wikipedia": f"https://ja.wikipedia.org/wiki/Special:Search?search={q_wiki}",
        "kotobank": f"https://kotobank.jp/word/{q_kotobank}",
        "jps": make_jps_about_url(word)
    }

    ndc_num = extract_ndc_number(word)
    if ndc_num:
        res["ndc"] = make_ndc_navi_url(ndc_num)
        lbl_str, is_exact, parent_c = resolve_ndc_label(ndc_num)
        res["ndc_label"] = lbl_str if is_exact else f"上位: {parent_c} {lbl_str}"
        res["ndc_num"] = ndc_num

    auth_id = extract_ndlna_id(word)
    if auth_id:
        res["ndlna"] = make_ndlna_url(auth_id)
        res["ndlna_label"] = resolve_ndlna_label(auth_id)
        res["ndlna_id"] = auth_id

    return res


def make_rich_search_links_md(word: str) -> str:
    """マークダウン形式の複数検索リンク文字列を生成 (NDC / NDLNA は公式リンクを最優先付与)"""
    links = make_rich_search_links(word)
    
    parts = [
        f"[🔍 Google]({links['google']})",
        f"[📖 Wikipedia]({links['wikipedia']})",
        f"[📚 コトバンク]({links['kotobank']})",
        f"[🏛️ ジャパンサーチ]({links['jps']})"
    ]

    if "ndlna" in links and links["ndlna"]:
        auth_id = links["ndlna_id"]
        lbl_part = f" 「{links['ndlna_label']}」" if links.get("ndlna_label") else ""
        parts.insert(0, f"[👥 **Web NDL Authorities ({auth_id}{lbl_part})**]({links['ndlna']})")
    elif "ndc" in links and links["ndc"]:
        ndc_num = links["ndc_num"]
        lbl_part = f" 「{links['ndc_label']}」" if links.get("ndc_label") else ""
        parts.insert(0, f"[🏷️ **NDC Navi 9版 ({ndc_num}{lbl_part})**]({links['ndc']}) ｜ [🌐 10版](https://ndcnavi.i.omu.ac.jp/#/)")

    return " ｜ ".join(parts)


def safe_save_json(data, target_path: str) -> bool:
    """
    データ構造（dict/list等）を一時ファイルに書き出してからアトミックにリネーム保存。
    書き込み途中の破損を防ぐ。
    """
    try:
        dir_name = os.path.dirname(target_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_path, target_path)
        return True
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
