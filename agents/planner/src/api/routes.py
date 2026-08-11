import logging

from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from configs.settings import settings
from pipeline import PlannerPipeline

logger = logging.getLogger("planner_api")

router = APIRouter()
pipeline = PlannerPipeline(verbose=settings.planner_verbose)


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "planner-agent"}


@router.post("/query", response_model=QueryResponse)
async def query_planner(request: QueryRequest):
    try:
        return await pipeline.run(request)
    except Exception as err:
        logger.exception("Errore durante l'elaborazione della richiesta planner")
        raise HTTPException(status_code=500, detail="Errore interno del planner-agent") from err