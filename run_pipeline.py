#!/usr/bin/env python3
"""CLI entry point: run the Nexus CPG demand + economic profiling pipeline
over the sample dataset and validate the output against answer_key/.

Usage:
    python run_pipeline.py [data_dir] [out_dir]
"""
from __future__ import annotations

import sys

import pandas as pd

from nexus_engine import pipeline, validate

DEFAULT_DATA_DIR = "nexus_cpg_sample_data_v1"
DEFAULT_OUT_DIR = "output"


def main() -> int:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA_DIR
    out_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT_DIR

    print(f"Running pipeline: data_dir={data_dir!r} out_dir={out_dir!r} asof={pipeline.DEFAULT_ASOF.date()}")
    tables = pipeline.run(data_dir, out_dir)
    for name, df in tables.items():
        print(f"  wrote {name}.csv  ({len(df)} rows)")

    print("\n--- Validation against answer_key/ ---")

    gf = validate.validate_golden_fixtures(data_dir)
    print("\nGolden fixtures (§5):")
    print(gf.to_string(index=False))
    n_fail = (~gf["match"]).sum()
    print(f"  -> {len(gf) - n_fail}/{len(gf)} fixtures match exactly")

    mismatched = validate.reconcile_true_demand(tables["daily_demand"], data_dir)
    print(f"\ntrue_demand_daily reconciliation: {mismatched} mismatched rows on feed-complete days (0 = clean)")

    qc = validate.compare_quick_check(tables["demand_profile"], data_dir)
    print("\nquick_check_90d comparison:")
    print(qc[["sku_code", "store_id", "N_expected", "N_ours", "K_expected", "K_ours", "observed_class", "demand_class", "N_match", "K_match", "class_match"]].to_string(index=False))
    all_n = qc["N_match"].all()
    all_k = qc["K_match"].all()
    all_c = qc["class_match"].all()
    print(f"  -> N match: {all_n}, K match: {all_k}, class match: {all_c}")

    ok = (n_fail == 0) and (mismatched == 0) and all_n and all_k and all_c
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
