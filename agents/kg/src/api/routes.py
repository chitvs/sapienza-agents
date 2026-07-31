import time
from fastapi import APIRouter, HTTPException
from api.schemas import QueryRequest, QueryResponse
from pipeline import KGPipeline

router = APIRouter()
pipeline = KGPipeline()

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "kg-agent"}

@router.post("/query", response_model=QueryResponse)
def query_kg(request: QueryRequest):
    try:
        start_time = time.time()
        target_kg = request.target_kg or "wikidata"
        pipeline.target_kg = target_kg
        results, query = pipeline.run(request.question)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        confidence_score = 1.0 if results else 0.0

        return QueryResponse(
            question=request.question,
            target_kg=target_kg,
            generated_query=query,
            results=results,
            count=len(results),
            confidence=confidence_score,
            execution_time_ms=elapsed_ms,
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
