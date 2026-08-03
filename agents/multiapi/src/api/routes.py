import time
from fastapi import APIRouter, HTTPException
from api.schemas import QueryRequest, QueryResponse
from pipeline import MultiApiPipeline

router = APIRouter()

pipeline = MultiApiPipeline(verbose=True)
"""Creo la pipeline una sola volta quando parte il server e non ad ogni richiesta """

#Definisco i 2 endpoint HTTP: healt e query

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "multiapi-agent"}


@router.post("/query", response_model=QueryResponse)
def query_multiapi(request: QueryRequest):
    try:
        start_time = time.time()
        results, intent = pipeline.run(request.question)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        confidence = 1.0 if results and "error" not in results[0] else 0.0

        return QueryResponse(
            question=request.question,
            intent=intent,
            results=results,
            count=len(results),
            confidence=confidence,
            execution_time_ms=elapsed_ms,
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
