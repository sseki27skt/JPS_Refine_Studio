# -*- coding: utf-8 -*-
"""
JS-Refine Studio - 統一デザインシステム ＆ スタイル定義モジュール
GEMINI.md の「UI / UX デザインシステム（脱『AIが作った感』の指針）」に準拠
"""
import streamlit as st


def inject_custom_css():
    """統一デザイントークン ＆ コンポーネントCSSを注入"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

    :root {
        --color-bg: #F8FAFC;
        --color-surface: #FFFFFF;
        --color-surface-subtle: #F1F5F9;
        --color-border: #E2E8F0;
        --color-border-subtle: #CBD5E1;
        --color-text-primary: #0F172A;
        --color-text-secondary: #334155;
        --color-text-muted: #64748B;
        --color-accent: #2563EB;
        --color-accent-dark: #1E293B;

        --color-status-pass: #059669;
        --color-status-pass-bg: #ECFDF5;
        --color-status-pass-border: #A7F3D0;

        --color-status-reject: #BE123C;
        --color-status-reject-bg: #FFF1F2;
        --color-status-reject-border: #FECDD3;

        --color-status-warn: #D97706;
        --color-status-warn-bg: #FFFBEB;
        --color-status-warn-border: #FDE68A;

        --color-status-neutral: #475569;
        --color-status-neutral-bg: #F1F5F9;
        --color-status-neutral-border: #CBD5E1;

        --radius-sm: 4px;
        --radius-md: 6px;
        --font-family: 'Plus Jakarta Sans', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --color-bg: #0F172A;
            --color-surface: #1E293B;
            --color-surface-subtle: #334155;
            --color-border: #334155;
            --color-border-subtle: #475569;
            --color-text-primary: #F8FAFC;
            --color-text-secondary: #CBD5E1;
            --color-text-muted: #94A3B8;

            --color-status-pass: #34D399;
            --color-status-pass-bg: rgba(5, 150, 105, 0.15);
            --color-status-pass-border: rgba(52, 211, 153, 0.3);

            --color-status-reject: #FB7185;
            --color-status-reject-bg: rgba(190, 18, 60, 0.15);
            --color-status-reject-border: rgba(251, 113, 133, 0.3);

            --color-status-warn: #FBBF24;
            --color-status-warn-bg: rgba(217, 119, 6, 0.15);
            --color-status-warn-border: rgba(251, 191, 36, 0.3);

            --color-status-neutral: #94A3B8;
            --color-status-neutral-bg: rgba(71, 85, 105, 0.25);
            --color-status-neutral-border: #475569;
        }
    }

    html, body, [class*="css"] {
        font-family: var(--font-family);
        color: var(--color-text-primary);
    }

    /* レイアウトシフト・ブレの防止 */
    html, body, section.main {
        scroll-behavior: auto !important;
    }

    div[data-testid="stAppViewBlockContainer"] {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
    }

    /* 汎用ボタンスタイル */
    button, [data-testid="stButton"] button {
        border-radius: var(--radius-sm) !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        transition: all 0.15s ease-in-out !important;
    }

    /* メトリック表示カード */
    div[data-testid="stMetric"] {
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 12px 16px;
        box-shadow: none;
    }

    div[data-testid="stMetric"] label {
        color: var(--color-text-muted) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
    }

    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        color: var(--color-text-primary) !important;
    }

    /* サイドバー */
    [data-testid="stSidebar"] {
        border-right: 1px solid var(--color-border);
        background-color: var(--color-surface);
    }

    /* コンテナ枠（border=True の標準コンテナ） */
    div[data-testid="stVerticalBlock"] > div[data-testid="stContainer"][border="true"] {
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-md) !important;
        background: var(--color-surface);
        padding: 16px 20px;
    }

    /* ヒーローカードバナー (学術・プロフェッショナル調) */
    .cleanse-hero {
        background: var(--color-accent-dark);
        border: 1px solid var(--color-border);
        color: #F8FAFC;
        border-radius: var(--radius-md);
        padding: 22px 26px;
        margin-bottom: 20px;
    }

    .cleanse-hero h1 {
        color: #F8FAFC !important;
        font-size: 1.55rem;
        font-weight: 700;
        margin: 0 0 6px 0;
        letter-spacing: -0.01em;
    }

    .cleanse-hero p {
        color: #94A3B8;
        font-size: 0.92rem;
        margin: 0;
        line-height: 1.55;
    }

    /* 汎用クレンジングカード */
    .cleanse-card {
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    /* ステータスバッジ（統一規格） */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 8px;
        border-radius: var(--radius-sm);
        font-size: 0.75rem;
        font-weight: 600;
        line-height: 1.4;
        border: 1px solid transparent;
        white-space: nowrap;
    }

    .status-badge-pass {
        background: var(--color-status-pass-bg);
        color: var(--color-status-pass);
        border-color: var(--color-status-pass-border);
    }

    .status-badge-reject {
        background: var(--color-status-reject-bg);
        color: var(--color-status-reject);
        border-color: var(--color-status-reject-border);
    }

    .status-badge-warn {
        background: var(--color-status-warn-bg);
        color: var(--color-status-warn);
        border-color: var(--color-status-warn-border);
    }

    .status-badge-neutral {
        background: var(--color-status-neutral-bg);
        color: var(--color-status-neutral);
        border-color: var(--color-status-neutral-border);
    }

    .status-badge-accent {
        background: rgba(37, 99, 235, 0.1);
        color: var(--color-accent);
        border-color: rgba(37, 99, 235, 0.3);
    }

    /* 警告・通知バナー（原色フラッシュ排除） */
    .warning-banner {
        background: var(--color-status-reject-bg);
        border-left: 4px solid var(--color-status-reject);
        border-top: 1px solid var(--color-status-reject-border);
        border-right: 1px solid var(--color-status-reject-border);
        border-bottom: 1px solid var(--color-status-reject-border);
        border-radius: var(--radius-sm);
        padding: 14px 18px;
        margin-bottom: 14px;
    }

    .warning-banner h4 {
        color: var(--color-status-reject);
        font-size: 0.95rem;
        font-weight: 700;
        margin: 0 0 6px 0;
    }

    .warning-banner p {
        margin: 0;
        font-size: 0.88rem;
        color: var(--color-text-secondary);
        line-height: 1.55;
    }

    .info-banner {
        background: var(--color-surface-subtle);
        border-left: 4px solid var(--color-accent);
        border-top: 1px solid var(--color-border);
        border-right: 1px solid var(--color-border);
        border-bottom: 1px solid var(--color-border);
        border-radius: var(--radius-sm);
        padding: 12px 16px;
        margin-bottom: 14px;
        font-size: 0.88rem;
        color: var(--color-text-secondary);
        line-height: 1.5;
    }

    /* ワークスペースカード */
    .ws-card {
        border: 1px solid var(--color-border);
        background: var(--color-surface);
        border-radius: var(--radius-md);
        padding: 14px 16px;
        margin-bottom: 10px;
        min-height: 165px;
    }

    .ws-card.active {
        border-color: var(--color-accent);
        background: rgba(37, 99, 235, 0.03);
    }

    .ws-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .ws-card-title {
        margin: 0;
        font-size: 1.0rem;
        font-weight: 600;
        color: var(--color-text-primary);
    }

    .ws-card-id {
        font-size: 0.8rem;
        color: var(--color-text-muted);
        margin-top: 2px;
    }

    .ws-card-theme {
        font-size: 0.8rem;
        color: var(--color-accent);
        margin-top: 4px;
    }

    .ws-card-desc {
        font-size: 0.85rem;
        color: var(--color-text-secondary);
        margin-top: 6px;
        line-height: 1.4;
        height: 36px;
        overflow: hidden;
    }

    .ws-card-meta {
        font-size: 0.75rem;
        color: var(--color-text-muted);
        margin-top: 8px;
    }

    /* スナップショット（履歴）カード */
    .snapshot-card {
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-left: 3px solid var(--color-accent);
        border-radius: var(--radius-md);
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    .snapshot-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .snapshot-title {
        font-weight: 600;
        font-size: 1.0rem;
        color: var(--color-text-primary);
    }

    .snapshot-date {
        font-size: 0.8rem;
        color: var(--color-text-muted);
    }

    .snapshot-desc {
        font-size: 0.85rem;
        color: var(--color-text-secondary);
        margin-top: 4px;
    }

    .snapshot-metrics {
        margin-top: 8px;
        display: flex;
        gap: 16px;
        font-size: 0.8rem;
    }

    .snapshot-metric-pass {
        color: var(--color-status-pass);
        font-weight: 500;
    }

    .snapshot-metric-reject {
        color: var(--color-status-reject);
        font-weight: 500;
    }

    .snapshot-metric-warn {
        color: var(--color-status-warn);
        font-weight: 500;
    }

    .snapshot-metric-muted {
        color: var(--color-text-muted);
    }

    .hero-sub {
        margin-top: 10px;
        color: #cbd5e1;
        font-size: 0.90rem;
        line-height: 1.6;
    }

    /* ファセット／ピルボードステータスバー */
    .facet-status-bar {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 0 10px 0;
        font-size: 0.88rem;
        color: var(--color-text-secondary);
    }

    .facet-counter {
        font-weight: 600;
        color: var(--color-text-primary);
    }

    .facet-draft-indicator {
        font-size: 0.82rem;
        font-weight: 600;
        color: var(--color-status-warn);
    }

    .facet-hint {
        font-size: 0.80rem;
        color: var(--color-text-muted);
    }

    /* グローバル・パイプライン・ステータスバー (画面上部) */
    .pipeline-bar-container {
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 10px 16px;
        margin-bottom: 18px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }

    .pipeline-bar-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 8px;
        margin-bottom: 8px;
        border-bottom: 1px solid var(--color-border-subtle);
        font-size: 0.82rem;
    }

    .pipeline-ws-tag {
        font-weight: 600;
        color: var(--color-text-primary);
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .pipeline-survival-metrics {
        color: var(--color-text-secondary);
        font-size: 0.80rem;
    }

    .pipeline-survival-count {
        font-weight: 700;
        color: var(--color-status-pass);
    }

    .pipeline-steps-wrapper {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 6px;
        overflow-x: auto;
    }

    .pipeline-step-node {
        flex: 1;
        min-width: 100px;
        padding: 6px 10px;
        border-radius: var(--radius-sm);
        border: 1px solid var(--color-border);
        background: var(--color-bg);
        text-align: center;
        font-size: 0.78rem;
        line-height: 1.35;
        transition: all 0.15s ease-in-out;
    }

    .pipeline-step-node.active {
        border-color: var(--color-accent);
        background: rgba(37, 99, 235, 0.08);
        box-shadow: 0 0 0 1px var(--color-accent);
    }

    .pipeline-step-node.completed {
        border-color: var(--color-status-pass-border);
        background: var(--color-status-pass-bg);
    }

    .pipeline-step-node.pending {
        opacity: 0.75;
    }

    .pipeline-step-title {
        font-weight: 600;
        color: var(--color-text-primary);
        display: block;
        margin-bottom: 2px;
    }

    .pipeline-step-count {
        font-size: 0.72rem;
        color: var(--color-text-muted);
    }

    .pipeline-step-node.completed .pipeline-step-count {
        color: var(--color-status-pass);
        font-weight: 500;
    }

    .pipeline-step-node.active .pipeline-step-count {
        color: var(--color-accent);
        font-weight: 600;
    }

    .pipeline-arrow {
        color: var(--color-border-subtle);
        font-size: 0.75rem;
        flex-shrink: 0;
    }

    /* コンテキスト・ガイダンスカード (各画面冒頭) */
    .guide-card {
        background: var(--color-surface);
        border: 1px solid var(--color-border);
        border-left: 4px solid var(--color-accent);
        border-radius: var(--radius-md);
        padding: 12px 18px;
        margin-bottom: 18px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
    }

    .guide-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
    }

    .guide-title {
        font-size: 0.92rem;
        font-weight: 700;
        color: var(--color-text-primary);
        margin: 0;
    }

    .guide-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 8px 16px;
        font-size: 0.83rem;
        line-height: 1.5;
    }

    .guide-item {
        display: flex;
        align-items: baseline;
        gap: 6px;
    }

    .guide-label {
        font-weight: 600;
        color: var(--color-text-secondary);
        white-space: nowrap;
        flex-shrink: 0;
        font-size: 0.78rem;
        background: var(--color-bg);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-sm);
        padding: 1px 6px;
    }

    .guide-text {
        color: var(--color-text-secondary);
        font-size: 0.83rem;
    }

    /* 完了サマリーアラート（控えめな成功バナー） */
    .summary-banner {
        background: var(--color-status-pass-bg);
        border: 1px solid var(--color-status-pass-border);
        border-left: 4px solid var(--color-status-pass);
        border-radius: var(--radius-sm);
        padding: 10px 16px;
        margin: 12px 0;
        font-size: 0.88rem;
        color: var(--color-status-pass);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .summary-banner-title {
        font-weight: 600;
    }

    .summary-banner-metrics {
        font-size: 0.82rem;
        color: var(--color-text-secondary);
    }

    /* 最下部ステップナビゲーションバー */
    .step-nav-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-top: 16px;
        margin-top: 24px;
        border-top: 1px solid var(--color-border);
    }
    </style>
    """, unsafe_allow_html=True)

