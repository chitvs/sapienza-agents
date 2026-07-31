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
        results, query = pipeline.run(request.question)
        return QueryResponse(
            question=request.question,
            target_kg="wikidata",
            generated_query=query,
            results=results,
            count=len(results),
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
