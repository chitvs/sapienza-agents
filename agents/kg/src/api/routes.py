import threading
import time

from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from configs.settings import settings
from connectors.base_connector import KnowledgeGraphUnavailableError
from executors.base_executor import QueryExecutionError
from pipeline import KGPipeline

router = APIRouter()

_pipelines: dict[str, KGPipeline] = {}
_pipelines_lock = threading.Lock()

def close_pipelines() -> None:
    """Chiude le risorse dei knowledge graph allo spegnimento del servizio."""
    with _pipelines_lock:
        for pipeline in _pipelines.values():
            close = getattr(pipeline.executor, "close", None)
            if callable(close):
                close()
        _pipelines.clear()

def get_pipeline(target_kg: str) -> KGPipeline:
    """Restituisce la pipeline del KG richiesto, creandola al primo utilizzo."""
    target_kg = (target_kg or "").strip().lower()
    with _pipelines_lock:
        if target_kg not in _pipelines:
            _pipelines[target_kg] = KGPipeline(target_kg=target_kg)
        return _pipelines[target_kg]

@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "kg-agent"}

@router.post("/query", response_model=QueryResponse)
def query_kg(request: QueryRequest) -> QueryResponse:
    target_kg = request.target_kg or settings.default_target_kg

    try:
        pipeline = get_pipeline(target_kg)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except (FileNotFoundError, ImportError) as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(
            status_code=503, detail=f"knowledge graph '{target_kg}' non disponibile: {err}"
        ) from err

    try:
        start_time = time.time()
        result = pipeline.run(request.question)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
    except KnowledgeGraphUnavailableError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except QueryExecutionError as err:
        raise HTTPException(status_code=503 if err.retryable else 500, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    return QueryResponse(
        question=request.question,
        target_kg=target_kg,
        generated_query=result.query,
        results=result.results,
        count=len(result.results),
        confidence=result.confidence,
        execution_time_ms=elapsed_ms,
        cached=result.cached,
    )
