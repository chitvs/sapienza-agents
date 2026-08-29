import time
from fastapi import APIRouter, HTTPException
from api.schemas import QueryRequest, QueryResponse
from configs.settings import settings
from pipeline import MultiApiPipeline

router = APIRouter()

pipeline = MultiApiPipeline(verbose=settings.verbose_pipeline)
"""Creo la pipeline una sola volta quando parte il server e non ad ogni richiesta """

#Definisco i 2 endpoint HTTP: health e query

@router.get("/health")
def health_check():
    """liveness più stato della configurazione.

    Lo stato resta "ok" anche senza chiave: il servizio risponde comunque su tre
    provider su quattro, e far fallire l'healthcheck bloccherebbe l'avvio
    dell'orchestratore. La configurazione mancante va però esposta, perché
    altrimenti si manifesta solo come errore a runtime su una singola domanda.
    """
    return {
        "status": "ok",
        "service": "multiapi-agent",
        "providers": {
            "weather": "ok",
            "exchange_rate": "ok",
            "country_info": "ok",
            "time_info": "ok" if settings.timeapi_api_key else "TIMEAPI_API_KEY mancante",
        },
    }


# exclude_none: i chiamanti verificano il fallimento con `if "error" in result`
# (vedi planner/src/tools.py), quindi la chiave non deve esistere a null.
@router.post("/query", response_model=QueryResponse, response_model_exclude_none=True)
def query_multiapi(request: QueryRequest):
    try:
        start_time = time.time()
        results, intent, cached, ignorati = pipeline.run(request.question)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        # se ogni risultato è in errore la risposta non è utilizzabile
        falliti = [r.get("error") for r in results if isinstance(r, dict) and r.get("error")]
        tutto_fallito = bool(results) and len(falliti) == len(results)
        # frazione di risultati validi: con un solo intent vale 1.0 o 0.0 come prima,
        # con più intent distingue una risposta completa da una a metà
        confidence = (len(results) - len(falliti)) / len(results) if results else 0.0

        return QueryResponse(
            question=request.question,
            intent=intent,
            results=results,
            count=len(results),
            confidence=confidence,
            execution_time_ms=elapsed_ms,
            cached=cached,
            ignored_intents=ignorati,
            error="; ".join(falliti) if tutto_fallito else None,
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
