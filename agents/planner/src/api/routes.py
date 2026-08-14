"""
Router delle API per il Planner Agent.

Definisce gli endpoint esposti dal microservizio, tra cui l'health check
e l'endpoint principale di query per l'elaborazione dei piani.
"""

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from configs.settings import settings
from pipeline import PlannerPipeline

logger = logging.getLogger("planner_api")

router: APIRouter = APIRouter()

# Istanziamo la pipeline a livello di modulo per riutilizzare l'oggetto
# e la sua cache interna dei prompt per tutte le richieste in entrata.
pipeline: PlannerPipeline = PlannerPipeline(verbose=settings.planner_verbose)


@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Endpoint di verifica dello stato del servizio.

    Returns:
        dict[str, str]: Un dizionario con lo stato 'ok' e il nome del servizio.
    """
    return {"status": "ok", "service": "planner-agent"}


@router.post("/query", response_model=QueryResponse)
async def query_planner(request: QueryRequest) -> QueryResponse:
    """
    Endpoint principale per la generazione e gestione dei piani.
    Riceve la richiesta, la passa alla pipeline e restituisce il piano strutturato.

    Args:
        request (QueryRequest): Il payload della richiesta contenente la domanda
        e gli eventuali hint di dominio, ID sessione o contesto.

    Returns:
        QueryResponse: La risposta strutturata finale elaborata dalla pipeline.

    Raises:
        HTTPException: Solleva un errore 500 se la pipeline fallisce in modo imprevisto.
    """
    try:
        return await pipeline.run(request)
    except Exception as err:
        # Catturiamo qualsiasi eccezione imprevista loggandone il traceback 
        # (tramite logger.exception) per evitare di esporre stack trace o
        # dettagli interni del sistema al client.
        logger.exception("Errore durante l'elaborazione della richiesta planner")
        raise HTTPException(
            status_code=500, 
            detail="Errore interno del planner-agent"
        ) from err