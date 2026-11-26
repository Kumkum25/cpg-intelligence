"""Lightweight, pipeline-independent data-quality checks used by the Data
Management page before anyone commits to running the full profiling
pipeline: does the file exist, does it have the right columns, how many
duplicate/missing rows does it have.
"""
from __future__ import annotations

import os

import pandas as pd

from . import config


def check_file(data_dir: str, filename: str) -> dict:
    path = os.path.join(data_dir, filename)
    required_cols = config.REQUIRED_COLUMNS.get(filename, [])

    if not os.path.exists(path):
        return {"file": filename, "present": False, "issues": ["file not found"]}

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except Exception as exc:
        return {"file": filename, "present": True, "issues": [f"failed to parse: {exc}"]}

    missing_cols = [c for c in required_cols if c not in df.columns]
    null_counts = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
    dup_rows = int(df.duplicated().sum())

    issues = []
    if missing_cols:
        issues.append(f"missing required columns: {missing_cols}")
    if dup_rows:
        issues.append(f"{dup_rows} fully duplicate rows")

    return {
        "file": filename,
        "present": True,
        "rows": len(df),
        "columns": list(df.columns),
        "missing_required_columns": missing_cols,
        "null_counts": null_counts,
        "duplicate_rows": dup_rows,
        "issues": issues,
    }


def check_all(data_dir: str) -> dict:
    results = [check_file(data_dir, f) for f in config.REQUIRED_RAW_FILES]
    ok = all(r["present"] and not r.get("missing_required_columns") for r in results)
    return {"data_dir": data_dir, "all_required_files_ok": ok, "files": results}
