from fastapi import APIRouter, Depends, HTTPException

from assistant import EXAMPLE_QUESTIONS, answer_question

from ..schemas import LLMAskRequest
from ..state import AppState, get_state

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/examples")
def examples():
    return {"example_questions": EXAMPLE_QUESTIONS}


@router.post("/ask")
def ask(req: LLMAskRequest, state: AppState = Depends(get_state)):
    if not state.loaded:
        raise HTTPException(409, "Pipeline has not been run yet. Call POST /data/pipeline/run first.")
    context = {"store_id": req.store_id, "sku_code": req.sku_code}
    return answer_question(req.question, state, context)
