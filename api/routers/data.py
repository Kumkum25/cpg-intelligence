"""Data Management endpoints: upload raw CSVs, validate them, inspect
quality, and (re)run the pipeline. Uploaded files land in NEXUS_UPLOAD_DIR
and never overwrite the bundled sample dataset or its answer_key/.
"""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config
from ..data_quality import check_all, check_file
from ..schemas import PipelineRunRequest
from ..state import AppState, get_state

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), dataset_name: str = Form(...)):
    if dataset_name not in config.REQUIRED_COLUMNS:
        raise HTTPException(400, f"Unknown dataset_name {dataset_name!r}. Expected one of {list(config.REQUIRED_COLUMNS)}")

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(config.UPLOAD_DIR, dataset_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    report = check_file(config.UPLOAD_DIR, dataset_name)
    return {"saved_to": dest, "quality_report": report}


@router.get("/status")
def data_status(data_dir: str | None = None, state: AppState = Depends(get_state)):
    return check_all(data_dir or state.data_dir)


@router.get("/uploaded-status")
def uploaded_status():
    """Quality report for whatever has been uploaded to NEXUS_UPLOAD_DIR so
    far, independent of what the pipeline is currently configured to read.
    """
    return check_all(config.UPLOAD_DIR)


@router.post("/pipeline/run")
def run_pipeline(req: PipelineRunRequest, state: AppState = Depends(get_state)):
    try:
        result = state.run_pipeline(data_dir=req.data_dir, asof=req.asof)
    except Exception as exc:
        raise HTTPException(400, f"Pipeline run failed: {exc}") from exc
    return result
