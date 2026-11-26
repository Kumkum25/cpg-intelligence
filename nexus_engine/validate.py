"""Checks pipeline output against the answer_key/ fixtures. Never read these
answer_key files from the production pipeline itself — validation only.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .classify import ADI_THRESHOLD, CV2_THRESHOLD, HIGH_CONFIDENCE_K


def _classify_fixture(y: np.ndarray) -> dict:
    N = len(y)
    z = y[y > 0]
    K = len(z)
    adi = N / K
    cv2 = float(z.var(ddof=0) / z.mean() ** 2)
    if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
        cls = "SMOOTH"
    elif adi < ADI_THRESHOLD:
        cls = "ERRATIC"
    elif cv2 < CV2_THRESHOLD:
        cls = "INTERMITTENT"
    else:
        cls = "LUMPY"
    conf = "HIGH" if K >= HIGH_CONFIDENCE_K else "PROVISIONAL"
    return dict(N=N, K=K, adi=round(adi, 6), cv2=round(cv2, 6), demand_class=cls, confidence=conf)


def validate_golden_fixtures(data_dir: str) -> pd.DataFrame:
    fixtures = pd.read_csv(os.path.join(data_dir, "golden_fixtures_28d.csv"))
    expected = pd.read_csv(os.path.join(data_dir, "answer_key", "golden_fixtures_expected.csv"))

    rows = []
    for fid, g in fixtures.groupby("fixture_id"):
        got = _classify_fixture(g["y"].to_numpy(dtype=float))
        exp = expected[expected["fixture_id"] == fid].iloc[0]
        match = (
            got["N"] == exp["N"] and got["K"] == exp["K"]
            and abs(got["adi"] - exp["adi"]) < 1e-6 and abs(got["cv2"] - exp["cv2"]) < 1e-6
            and got["demand_class"] == exp["demand_class"] and got["confidence"] == exp["class_confidence"]
        )
        rows.append({"fixture_id": fid, **got, "match": match})
    return pd.DataFrame(rows)


def reconcile_true_demand(daily_demand: pd.DataFrame, data_dir: str) -> int:
    """Confirms the cleaned/aggregated gross-demand series matches the
    answer key's `sold_ea` on every feed-complete day. Returns the count of
    mismatched rows (0 means the ingestion/cleaning logic is correct).
    """
    truth = pd.read_csv(os.path.join(data_dir, "answer_key", "true_demand_daily.csv"))
    calendar = pd.read_csv(os.path.join(data_dir, "store_calendar_feed_log.csv"))
    truth["date"] = pd.to_datetime(truth["date"])
    calendar["date"] = pd.to_datetime(calendar["date"])

    ours = daily_demand[["store_id", "sku_code", "date", "sold_ea"]].rename(columns={"sold_ea": "sold_ea_ours"})
    m = truth.merge(ours, on=["store_id", "sku_code", "date"], how="left")
    m["sold_ea_ours"] = m["sold_ea_ours"].fillna(0.0)
    m = m.merge(calendar[["store_id", "date", "pos_feed_received"]], on=["store_id", "date"], how="left")
    ok = m[m["pos_feed_received"] == True]  # noqa: E712
    return int((ok["sold_ea"] != ok["sold_ea_ours"]).sum())


def compare_quick_check(demand_profile: pd.DataFrame, data_dir: str) -> pd.DataFrame:
    """Row-by-row comparison of our 90D profile vs answer_key/quick_check_90d.csv."""
    qc = pd.read_csv(os.path.join(data_dir, "answer_key", "quick_check_90d.csv"))
    ours = demand_profile[["store_id", "sku_code", "N_90d", "K_90d", "adi_90d", "cv2_90d", "demand_class_90d"]].rename(
        columns={"N_90d": "N", "K_90d": "K", "adi_90d": "adi", "cv2_90d": "cv2", "demand_class_90d": "demand_class"}
    )
    m = qc.merge(ours, on=["sku_code", "store_id"], suffixes=("_expected", "_ours"))
    m["N_match"] = m["N_expected"] == m["N_ours"]
    m["K_match"] = m["K_expected"] == m["K_ours"]
    m["class_match"] = m["observed_class"] == m["demand_class"]
    return m
