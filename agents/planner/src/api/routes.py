from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from pipeline import PlannerPipeline

router = APIRouter()
pipeline = PlannerPipeline(verbose=True)


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "planner-agent"}


@router.post("/query", response_model=QueryResponse)
def query_planner(request: QueryRequest):
    try:
        return pipeline.run(request)
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))