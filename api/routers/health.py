from fastapi import APIRouter, Depends

from ..state import AppState, get_state

router = APIRouter(tags=["health"])


@router.get("/health")
def health(state: AppState = Depends(get_state)):
    return {
        "status": "ok",
        "pipeline_loaded": state.loaded,
        "data_dir": state.data_dir,
        "asof": state.asof.strftime("%Y-%m-%d"),
        "last_error": state.last_error,
    }
