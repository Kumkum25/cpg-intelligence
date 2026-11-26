"""Small shared utilities used by both the API layer and the assistant
layer. Kept in nexus_engine since both of those depend on it already.
"""
from __future__ import annotations

import json
import math

import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe DataFrame -> list[dict]. Uses pandas' own ``to_json``
    (which correctly emits NaN as JSON null and handles numpy dtypes)
    instead of ``.where(df.notna(), None).to_dict(...)``, which silently
    fails to convert NaN in numeric columns because pandas re-coerces None
    back to NaN to preserve a float dtype.
    """
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


def safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f
