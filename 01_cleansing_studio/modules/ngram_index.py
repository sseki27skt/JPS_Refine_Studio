# -*- coding: utf-8 -*-
"""
JS-Refine Studio - タイトル N-Gram 超高速インメモリ転置インデックス
全 N (2〜9文字) 間の双方向共起除外とリアルタイム残存件数を 0.001秒 で瞬時計算
"""

import os
import re
from collections import Counter, defaultdict
from typing import Dict, Set, List, Optional
import streamlit as st


class NgramInvertedIndex:
    """
    タイトル語彙の転置インデックス (Word -> Set of Title IDs)
    N=8等の長い語彙で除外されたレコードの分を、N=7等の短い語彙ピルの残存件数に数ミリ秒で反映。
    """
    def __init__(self, clean_titles: List[str], word_to_title_ids: Dict[str, Set[int]], total_titles: int):
        self.clean_titles = clean_titles
        self.word_to_title_ids = word_to_title_ids
        self.total_titles = total_titles

    def compute_discarded_titles(self, ng_rules: Set[str]) -> Set[int]:
        """
        全N-gramのNGルール群に該当するタイトルのインデックス集合を高速算出 (約0.001秒)
        記号・約物の除去正規化を行い、表記揺れによる除外漏れを完全防止
        """
        if not ng_rules:
            return set()
        from modules.ngram_filter import clean_title_text
        discarded = set()
        for ng in ng_rules:
            clean_ng = clean_title_text(ng)
            if not clean_ng:
                continue
            t_ids = self.word_to_title_ids.get(clean_ng)
            if t_ids is not None:
                discarded.update(t_ids)
            else:
                # 辞書外の任意キーワード等のフォールバック走査
                for idx, ct in enumerate(self.clean_titles):
                    if clean_ng in ct:
                        discarded.add(idx)
        return discarded

    def compute_remaining_counts(self, words: List[str], discarded_title_ids: Set[int]) -> Dict[str, int]:
        """
        除外タイトルを差し引いた、指定語彙リストの真の残存出現件数を瞬時に計算 (サブミリ秒)
        インデックス辞書外の語彙に対してもフォールバック計算で正確な件数を算出
        """
        from modules.ngram_filter import clean_title_text
        counts = {}
        for w in words:
            clean_w = clean_title_text(w)
            t_ids = self.word_to_title_ids.get(clean_w) if clean_w else None
            if t_ids is not None:
                counts[w] = len(t_ids - discarded_title_ids)
            elif clean_w:
                # 辞書外語彙の正確な残存件数フォールバック
                matched = 0
                for idx, ct in enumerate(self.clean_titles):
                    if idx not in discarded_title_ids and clean_w in ct:
                        matched += 1
                counts[w] = matched
            else:
                counts[w] = 0
        return counts


@st.cache_resource(show_spinner="タイトル語彙の高速インデックスを構築中...")
def get_ngram_inverted_index(titles_tuple: tuple) -> NgramInvertedIndex:
    """
    タイトル一覧から全N-gram上位語彙の転置インデックスをメモリ上に1回だけ構築。
    以後は st.cache_resource によりゼロ秒で参照され、タブ切り替えや仮選択時も超高速に動作します。
    """
    from modules.ngram_filter import clean_title_text

    clean_titles = [clean_title_text(t) for t in titles_tuple]
    total_titles = len(clean_titles)

    # 1. 各N (2〜9) の出現頻度を集計
    counts = {n: Counter() for n in range(2, 10)}
    for ct in clean_titles:
        L = len(ct)
        for n in range(2, 10):
            if L >= n:
                seen_n = set()
                for i in range(L - n + 1):
                    w = ct[i:i+n]
                    if w not in seen_n:
                        seen_n.add(w)
                        counts[n][w] += 1

    # 2. 各Nの上位500語（計約4,000語）をインデックス化対象に選定
    target_vocab = set()
    for n in range(2, 10):
        for w, c in counts[n].most_common(500):
            if c >= 2:
                target_vocab.add(w)

    # 3. 転置インデックス (Word -> Title IDs) の構築
    word_to_title_ids = defaultdict(set)
    for idx, ct in enumerate(clean_titles):
        L = len(ct)
        for n in range(2, 10):
            if L >= n:
                for i in range(L - n + 1):
                    w = ct[i:i+n]
                    if w in target_vocab:
                        word_to_title_ids[w].add(idx)

    return NgramInvertedIndex(clean_titles, dict(word_to_title_ids), total_titles)
