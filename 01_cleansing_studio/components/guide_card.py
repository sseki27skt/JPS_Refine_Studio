# -*- coding: utf-8 -*-
"""
コンテキスト・ガイダンス ＆ ナビゲーション コンポーネント
各ステップの冒頭に配置されるガイドカードと、最下部の次工程遷移ボタンを提供します。
"""
import streamlit as st
from typing import Optional


def render_guide_card(step_num: str, step_title: str, purpose: str, impact: str, condition: str):
    """
    画面冒頭に表示するコンパクトなコンテキスト・ガイダンスカード
    """
    card_html = f"""
    <div class="guide-card">
        <div class="guide-header">
            <span class="status-badge status-badge-accent">{step_num}</span>
            <h4 class="guide-title">{step_title}</h4>
        </div>
        <div class="guide-grid">
            <div class="guide-item">
                <span class="guide-label">目的</span>
                <span class="guide-text">{purpose}</span>
            </div>
            <div class="guide-item">
                <span class="guide-label">データ影響</span>
                <span class="guide-text">{impact}</span>
            </div>
            <div class="guide-item">
                <span class="guide-label">次への条件</span>
                <span class="guide-text">{condition}</span>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_summary_banner(title: str, metrics_text: str = ""):
    """
    処理完了時に表示する控えめなサマリーバナー
    """
    metrics_html = f"<span class='summary-banner-metrics'>{metrics_text}</span>" if metrics_text else ""
    banner_html = f"""
    <div class="summary-banner">
        <span class="summary-banner-title">{title}</span>
        {metrics_html}
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)


def navigate_to(target_choice: str):
    """
    指定した工程（画面）へ安全に遷移します。
    StreamlitWidgetAlreadyInstantiatedError を防止し、
    保留キューおよびセッションステートを安全に同期します。
    """
    st.session_state["nav_target"] = target_choice
    st.session_state["main_menu_choice"] = target_choice
    st.rerun()


def render_step_navigation(
    prev_choice: Optional[str] = None, 
    next_choice: Optional[str] = None, 
    prev_label: Optional[str] = None, 
    next_label: Optional[str] = None
):
    """
    各画面最下部に配置するステップナビゲーションバー
    """
    st.write("")
    st.write("---")

    col_prev, col_spacer, col_next = st.columns([3, 4, 3])

    with col_prev:
        if prev_choice:
            label = prev_label or f"前へ: {prev_choice.split(':')[0] if ':' in prev_choice else prev_choice}"
            if st.button(f"<- {label}", key=f"nav_prev_{prev_choice}", use_container_width=True):
                navigate_to(prev_choice)

    with col_next:
        if next_choice:
            label = next_label or f"次へ進む: {next_choice.split(':')[0] if ':' in next_choice else next_choice}"
            if st.button(f"{label} ->", key=f"nav_next_{next_choice}", type="primary", use_container_width=True):
                navigate_to(next_choice)
