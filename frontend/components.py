"""Reusable UI components for the Nexus CPG Intelligence design system.
Every page imports from here instead of hand-rolling HTML, so a palette or
spacing change in theme.py propagates everywhere automatically.
"""
from __future__ import annotations

import html as _html

import streamlit as st

from theme import (
    ACCENT_GRADIENT, CARD, CARD_BORDER, CRITICAL, NEUTRAL, SUCCESS, TEXT_FAINT,
    TEXT_MUTED, TEXT_PRIMARY, TONE_COLORS, WARNING,
)

GLOBAL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{
    background-color: #0A0E1A !important;
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
}}
[data-testid="stHeader"] {{ background-color: rgba(0,0,0,0) !important; }}
[data-testid="stToolbar"] {{ right: 1rem; }}
.block-container {{ padding-top: 1.6rem !important; padding-bottom: 2.5rem !important; max-width: 1400px; }}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {{
    background-color: #0F1527 !important;
    border-right: 1px solid {CARD_BORDER};
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem; }}
[data-testid="stSidebar"] button[kind="secondary"], [data-testid="stSidebar"] button[kind="primary"] {{
    text-align: left !important;
    justify-content: flex-start !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.92rem !important;
    padding: 0.55rem 0.9rem !important;
    margin-bottom: 2px;
    transition: background 0.15s ease, color 0.15s ease;
}}
[data-testid="stSidebar"] button[kind="secondary"] {{
    background: transparent !important;
    color: {TEXT_MUTED} !important;
    border: 1px solid transparent !important;
}}
[data-testid="stSidebar"] button[kind="secondary"]:hover {{
    background: #1A2240 !important;
    color: {TEXT_PRIMARY} !important;
}}
[data-testid="stSidebar"] button[kind="primary"] {{
    background: linear-gradient(135deg, rgba(139,108,246,0.25) 0%, rgba(78,124,246,0.25) 60%, rgba(34,211,238,0.22) 100%) !important;
    color: {TEXT_PRIMARY} !important;
    border: 1px solid rgba(139,108,246,0.45) !important;
    box-shadow: 0 0 0 1px rgba(139,108,246,0.15) inset;
}}

/* ---------- Headings ---------- */
h1, h2, h3 {{ color: {TEXT_PRIMARY} !important; font-weight: 700 !important; letter-spacing: -0.01em; }}
p, span, label, .stMarkdown, [data-testid="stCaptionContainer"] {{ color: {TEXT_MUTED}; }}
hr {{ border-color: {CARD_BORDER} !important; margin: 1.3rem 0 !important; }}

/* ---------- Buttons (main area) ---------- */
.main button[kind="primary"] {{
    background: {ACCENT_GRADIENT} !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 14px rgba(99,102,241,0.25);
}}
.main button[kind="secondary"] {{
    background: {CARD} !important;
    border: 1px solid {CARD_BORDER} !important;
    color: {TEXT_PRIMARY} !important;
    border-radius: 10px !important;
}}
.main button[kind="secondary"]:hover {{ border-color: #4E7CF6 !important; }}

/* ---------- Inputs ---------- */
[data-testid="stSelectbox"] > div > div, [data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input, [data-testid="stDateInput"] input,
[data-baseweb="select"] > div {{
    background-color: {CARD} !important;
    border-color: {CARD_BORDER} !important;
    color: {TEXT_PRIMARY} !important;
    border-radius: 9px !important;
}}

/* ---------- DataFrames / tables ---------- */
[data-testid="stDataFrame"] {{
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 12px !important;
    overflow: hidden;
}}

/* ---------- Expander ---------- */
[data-testid="stExpander"] {{
    background-color: {CARD} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 12px !important;
}}

/* ---------- Chat ---------- */
[data-testid="stChatMessage"] {{
    background-color: {CARD} !important;
    border: 1px solid {CARD_BORDER} !important;
    border-radius: 14px !important;
}}
[data-testid="stChatInput"] textarea {{
    background-color: {CARD} !important;
    border-color: {CARD_BORDER} !important;
    color: {TEXT_PRIMARY} !important;
}}

/* ---------- Metric (native, used sparingly) ---------- */
[data-testid="stMetric"] {{
    background-color: {CARD};
    border: 1px solid {CARD_BORDER};
    border-radius: 14px;
    padding: 0.9rem 1rem;
}}
[data-testid="stMetricValue"] {{ color: {TEXT_PRIMARY} !important; }}

/* ---------- Custom components ---------- */
.nx-kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 6px 0 18px 0; }}
.nx-card {{
    background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 16px;
    padding: 16px 18px; position: relative; overflow: hidden;
    transition: transform 0.15s ease, border-color 0.15s ease;
}}
.nx-card:hover {{ border-color: #3A4278; }}
.nx-kpi-icon {{ font-size: 1.3rem; opacity: 0.9; }}
.nx-kpi-label {{ color: {TEXT_MUTED}; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 6px; }}
.nx-kpi-value {{ color: {TEXT_PRIMARY}; font-size: 1.65rem; font-weight: 700; margin-top: 2px; line-height: 1.2; }}
.nx-kpi-sub {{ font-size: 0.78rem; font-weight: 600; margin-top: 4px; }}
.nx-kpi-bar {{ position: absolute; top: 0; left: 0; width: 4px; height: 100%; }}

.nx-page-header {{ margin-bottom: 1.4rem; }}
.nx-page-title {{ font-size: 1.9rem; font-weight: 800; color: {TEXT_PRIMARY}; margin: 0; letter-spacing: -0.02em; }}
.nx-page-subtitle {{ color: {TEXT_MUTED}; font-size: 0.95rem; margin-top: 4px; }}
.nx-page-icon-chip {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; border-radius: 12px; font-size: 1.3rem;
    background: {ACCENT_GRADIENT}; margin-right: 12px;
}}

.nx-section-title {{ color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 700; margin: 0 0 0.6rem 0; display: flex; align-items: center; gap: 8px; }}

.nx-badge {{
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 20px;
    font-size: 0.74rem; font-weight: 600; letter-spacing: 0.02em; white-space: nowrap;
}}

.nx-insight {{
    background: {CARD}; border: 1px solid {CARD_BORDER}; border-left: 3px solid #8B6CF6;
    border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
}}
.nx-insight-title {{ color: {TEXT_PRIMARY}; font-weight: 700; font-size: 0.92rem; margin-bottom: 4px; }}
.nx-insight-body {{ color: {TEXT_MUTED}; font-size: 0.88rem; line-height: 1.5; }}

.nx-status-pill {{
    display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 10px;
    background: {CARD}; border: 1px solid {CARD_BORDER}; font-size: 0.8rem; margin-bottom: 6px;
}}
.nx-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}

.nx-divider-label {{ color: {TEXT_FAINT}; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; margin: 1.6rem 0 0.6rem 0; }}
"""


def inject_global_css():
    st.html(f"<style>{GLOBAL_CSS}</style>")


def _tone_color(tone: str) -> str:
    return TONE_COLORS.get(tone, NEUTRAL)


def page_header(title: str, subtitle: str = "", icon: str = "📊"):
    st.html(f"""
    <div class="nx-page-header" style="display:flex; align-items:center;">
        <div class="nx-page-icon-chip">{icon}</div>
        <div>
            <div class="nx-page-title">{_html.escape(title)}</div>
            <div class="nx-page-subtitle">{_html.escape(subtitle)}</div>
        </div>
    </div>
    """)


def section_title(title: str, icon: str = ""):
    st.html(f'<div class="nx-section-title">{icon} {_html.escape(title)}</div>')


def divider_label(text: str):
    st.html(f'<div class="nx-divider-label">{_html.escape(text)}</div>')


def kpi_row(cards: list[dict]):
    """Each card: {label, value, icon, tone, sub}. Renders as one responsive grid."""
    items_html = []
    for c in cards:
        tone = c.get("tone", "neutral")
        color = _tone_color(tone)
        sub_html = f'<div class="nx-kpi-sub" style="color:{color};">{_html.escape(str(c["sub"]))}</div>' if c.get("sub") else ""
        items_html.append(f"""
        <div class="nx-card">
            <div class="nx-kpi-bar" style="background:{color};"></div>
            <div class="nx-kpi-icon">{c.get('icon', '◆')}</div>
            <div class="nx-kpi-label">{_html.escape(str(c['label']))}</div>
            <div class="nx-kpi-value">{_html.escape(str(c['value']))}</div>
            {sub_html}
        </div>
        """)
    st.html(f'<div class="nx-kpi-grid">{"".join(items_html)}</div>')


def badge(text: str, tone: str = "neutral") -> str:
    color = _tone_color(tone)
    return f'<span class="nx-badge" style="background:{color}22; color:{color}; border:1px solid {color}55;">{_html.escape(str(text))}</span>'


def badge_render(text: str, tone: str = "neutral"):
    st.html(badge(text, tone))


def insight_panel(title: str, body: str, icon: str = "💡"):
    st.html(f"""
    <div class="nx-insight">
        <div class="nx-insight-title">{icon} {_html.escape(title)}</div>
        <div class="nx-insight-body">{body}</div>
    </div>
    """)


def status_pill(label: str, ok: bool, detail: str = ""):
    color = SUCCESS if ok else CRITICAL
    st.html(f"""
    <div class="nx-status-pill">
        <span class="nx-dot" style="background:{color}; box-shadow: 0 0 6px {color};"></span>
        <span style="color:{TEXT_PRIMARY}; font-weight:600;">{_html.escape(label)}</span>
        <span style="color:{TEXT_MUTED};">{_html.escape(detail)}</span>
    </div>
    """)


def dataset_pill(is_sample: bool, name: str):
    color = "#4E7CF6" if is_sample else "#8B6CF6"
    icon = "🧪" if is_sample else "📦"
    label = "Sample Dataset" if is_sample else f"Uploaded: {name}"
    st.html(f"""
    <div class="nx-status-pill">
        <span style="font-size:0.95rem;">{icon}</span>
        <span style="color:{TEXT_PRIMARY}; font-weight:600;">{_html.escape(label)}</span>
    </div>
    """)
