from fastapi import APIRouter, HTTPException, status
from api.schemas import QueryRequest, QueryResponse
from pipeline import KGPipeline

router = APIRouter()

# istanza globale della pipeline gestita all'avvio dell'applicazione
_pipeline: KGPipeline | None = None

def set_pipeline(pipeline_instance: KGPipeline):
    global _pipeline
    _pipeline = pipeline_instance

def get_pipeline() -> KGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = KGPipeline()
    return _pipeline

@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """endpoint per l'healthcheck del microservizio."""
    current_pipeline = get_pipeline()
    if current_pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline non inizializzata",
        )
    return {"status": "ok", "service": "kg-agent"}

@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
def process_query(request: QueryRequest):
    """accetta una domanda in linguaggio naturale ed esegue il flusso knowledge graph QA completo."""
    current_pipeline = get_pipeline()

    try:
        results, last_query = current_pipeline.run(
            question=request.question,
        )
        return QueryResponse(
            question=request.question,
            target_kg=request.target_kg or "wikidata",
            generated_query=last_query,
            results=results,
            count=len(results),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'elaborazione della query: {str(e)}",
        )
