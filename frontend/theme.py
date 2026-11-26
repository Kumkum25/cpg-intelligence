"""Design tokens for the Nexus CPG Intelligence UI: one source of truth for
colors, spacing, and the Plotly template, so every page and component stays
visually consistent. Change a color here, it changes everywhere.
"""
from __future__ import annotations

# --- Core palette --------------------------------------------------------
BG = "#0A0E1A"            # app background — deep navy / near-black
SURFACE = "#0F1527"       # sidebar / secondary surface
CARD = "#141B30"          # elevated card background
CARD_BORDER = "#242C4D"   # subtle card border
CARD_HOVER = "#1A2240"

ACCENT_PURPLE = "#8B6CF6"
ACCENT_BLUE = "#4E7CF6"
ACCENT_CYAN = "#22D3EE"
ACCENT_GRADIENT = f"linear-gradient(135deg, {ACCENT_PURPLE} 0%, {ACCENT_BLUE} 55%, {ACCENT_CYAN} 100%)"

SUCCESS = "#34D399"
WARNING = "#FBBF24"
CRITICAL = "#F87171"
NEUTRAL = "#6B7494"

TEXT_PRIMARY = "#EDEFF7"
TEXT_MUTED = "#8B93B4"
TEXT_FAINT = "#5B6280"

TONE_COLORS = {
    "positive": SUCCESS, "success": SUCCESS,
    "warning": WARNING,
    "critical": CRITICAL, "danger": CRITICAL,
    "neutral": NEUTRAL, "info": ACCENT_BLUE,
    "purple": ACCENT_PURPLE, "blue": ACCENT_BLUE, "cyan": ACCENT_CYAN,
}

# Demand classification palette, reused across Overview / Demand pages / charts
CLASS_COLORS = {
    "SMOOTH": ACCENT_CYAN, "ERRATIC": WARNING, "INTERMITTENT": ACCENT_PURPLE,
    "LUMPY": CRITICAL, "DORMANT": TEXT_FAINT, "NOT_RANGED": "#3A4068", "INSUFFICIENT": NEUTRAL,
}

CHART_COLORWAY = [ACCENT_CYAN, ACCENT_PURPLE, ACCENT_BLUE, SUCCESS, WARNING, CRITICAL, "#60A5FA", "#C084FC"]

PLOTLY_LAYOUT = dict(
    paper_bgcolor=CARD,
    plot_bgcolor=CARD,
    font=dict(color=TEXT_MUTED, family="Inter, -apple-system, Segoe UI, sans-serif", size=12),
    colorway=CHART_COLORWAY,
    margin=dict(t=40, b=30, l=10, r=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_MUTED)),
    xaxis=dict(gridcolor=CARD_BORDER, zerolinecolor=CARD_BORDER, color=TEXT_MUTED, linecolor=CARD_BORDER),
    yaxis=dict(gridcolor=CARD_BORDER, zerolinecolor=CARD_BORDER, color=TEXT_MUTED, linecolor=CARD_BORDER),
    title=dict(font=dict(color=TEXT_PRIMARY, size=15)),
    hoverlabel=dict(bgcolor=SURFACE, font_color=TEXT_PRIMARY, bordercolor=CARD_BORDER),
)


def apply_theme(fig):
    """Apply the standard dark theme to any Plotly figure in-place-ish (returns it)."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig
