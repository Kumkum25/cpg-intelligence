"""Business-factor scaffold (Module 4).

This is deliberately a *registry*, not a model: each factor either has a
real data source wired up (right now, only price changes do — they're
derivable from ``sku_economics``) or is marked unavailable. Nothing here
fabricates a data source that doesn't exist. As real promo/marketing/
competitor/weather feeds become available, add a loader here and flip its
status to "available" — the forecast orchestrator doesn't need to change.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..ingest import RawData

# Factors we know CPG demand planners care about. Anything not wired to a
# real loader below stays explicitly "unavailable" rather than guessed at.
KNOWN_FACTORS = [
    "price_change", "promotions", "marketing_activity", "competitor_activity",
    "weather", "distribution_changes", "cannibalization",
]


@dataclass
class FactorStatus:
    name: str
    available: bool
    source: str | None
    note: str


def factor_availability(raw: RawData) -> list[FactorStatus]:
    return [
        FactorStatus("price_change", True, "sku_economics.csv",
                     "Derived from effective-dated price changes already in the economic data."),
        FactorStatus("promotions", False, None,
                     "No promo calendar or discount flag in the source data. Would need a promo feed keyed by store/sku/date."),
        FactorStatus("marketing_activity", False, None,
                     "No marketing spend/activity feed available."),
        FactorStatus("competitor_activity", False, None,
                     "No competitor pricing or distribution feed available."),
        FactorStatus("weather", False, None,
                     "No weather feed available. Would help explain some of the seasonal SKUs' residual variance."),
        FactorStatus("distribution_changes", False, None,
                     "No ranging/distribution-change event feed beyond the ranging.csv ranged_from/ranged_to dates already used in demand profiling."),
        FactorStatus("cannibalization", False, None,
                     "No product-substitution or basket data available to estimate cross-SKU effects."),
    ]


def price_change_history(raw: RawData, store_id: str, sku_code: str) -> pd.DataFrame:
    """Actual price-change events for one store/sku, derived from
    sku_economics (joined through location -> channel). Real data, not an
    assumption — this is what distinguishes it from the other factors.
    """
    channel = raw.location.loc[raw.location["store_id"] == store_id, "channel"].iloc[0]
    rows = raw.sku_economics[(raw.sku_economics["sku_code"] == sku_code) & (raw.sku_economics["channel_id"] == channel)]
    rows = rows.sort_values("effective_from")[["effective_from", "effective_to", "net_price_per_ea"]]
    rows["pct_change_from_prior"] = rows["net_price_per_ea"].pct_change().round(4)
    return rows.reset_index(drop=True)


def simulate_price_change(baseline_forecast: np.ndarray, price_change_pct: float, assumed_elasticity: float | None) -> dict:
    """Scenario analysis: 'what if price moves by X%?'

    We will NOT invent an elasticity. If the caller doesn't supply one, the
    forecast is returned unchanged with an explicit note — a silent "no
    effect" assumption is still an assumption, so we say so rather than
    implying the model accounted for it.
    """
    if assumed_elasticity is None:
        return {
            "adjusted_forecast": baseline_forecast.tolist(),
            "price_change_pct": price_change_pct,
            "assumed_elasticity": None,
            "note": (
                "No price elasticity was supplied and none could be estimated from this dataset "
                "(it has no historical instance of a price change with enough surrounding stable "
                "volume to isolate its demand effect). The forecast below is UNCHANGED from baseline — "
                "it does not reflect the price move. Supply an elasticity assumption to see an adjusted estimate."
            ),
        }
    demand_change_pct = assumed_elasticity * price_change_pct
    adjusted = np.clip(baseline_forecast * (1 + demand_change_pct), 0, None)
    return {
        "adjusted_forecast": adjusted.tolist(),
        "price_change_pct": price_change_pct,
        "assumed_elasticity": assumed_elasticity,
        "implied_demand_change_pct": round(demand_change_pct, 4),
        "note": (
            f"Adjusted using a user-supplied elasticity assumption ({assumed_elasticity}), "
            "not a value estimated from historical data. Treat this as a what-if scenario, not a prediction."
        ),
    }
