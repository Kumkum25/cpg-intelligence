"""Export endpoints — streams a computed table back as CSV or XLSX. These
read only from state.tables (already-computed pipeline output); nothing
here recalculates anything.
"""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..state import AppState, get_state

router = APIRouter(prefix="/reports", tags=["reports"])

EXPORTABLE_TABLES = [
    "daily_demand", "daily_returns", "daily_panel", "demand_profile", "economic_profile", "supplier_profile",
    "model_recommendations", "bulk_forecast",
]


def _lookup_table(table_name: str, state: AppState) -> pd.DataFrame | None:
    if table_name == "model_recommendations":
        return state.recommendations
    if table_name == "bulk_forecast":
        return state.bulk_forecast
    return state.tables.get(table_name)


@router.get("/tables")
def list_tables():
    return {"exportable_tables": EXPORTABLE_TABLES}


@router.get("/export/{table_name}")
def export_table(table_name: str, format: str = "csv", state: AppState = Depends(get_state)):
    if table_name not in EXPORTABLE_TABLES:
        raise HTTPException(404, f"Unknown table {table_name!r}. Choose from {EXPORTABLE_TABLES}")
    if not state.loaded:
        raise HTTPException(409, "Pipeline has not been run yet.")

    df = _lookup_table(table_name, state)
    if df is None:
        raise HTTPException(409, f"'{table_name}' has not been computed yet.")

    if format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table_name}.csv"},
        )
    elif format == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=table_name[:31])
        buf.seek(0)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={table_name}.xlsx"},
        )
    raise HTTPException(400, "format must be 'csv' or 'xlsx'")
