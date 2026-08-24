"""
Router delle API per il Planner Agent.

Definisce gli endpoint esposti dal microservizio, tra cui l'health check
e l'endpoint principale di query per l'elaborazione dei piani.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import ModelInfo, ModelsResponse, QueryRequest, QueryResponse, ToolInfo
from configs.settings import settings
from pipeline import PlannerPipeline
from tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY

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


async def _available_models() -> list[ModelInfo]:
    """
    Effettua l'auto-discovery asincrono dei modelli su Ollama e Gemini
    e carica i modelli OpenRouter configurati.
    """
    models: list[ModelInfo] = []
    from http_client import get_http_client
    client = get_http_client()
    
    # 1. Ollama (Discovery in locale, non bloccante)
    try:
        resp = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags", timeout=1.5)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                models.append(ModelInfo(id=f"ollama/{m['name']}", provider="ollama", model=m["name"]))
    except Exception as e:
        logger.warning(f"Auto-discovery Ollama fallito: {e}")

    # 2. Gemini (Discovery su Google AI Studio, non bloccante)
    if settings.gemini_api_key:
        try:
            url = f"{settings.gemini_api_base}/models?key={settings.gemini_api_key}"
            resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                # Escludiamo modelli audio, immagini, video e agentici/sperimentali non adatti al task JSON
                excluded_keywords = [
                    "tts", "image", "lyria", "robotics", "antigravity", 
                    "deep-research", "computer-use", "banana", "customtools"
                ]
                for m in resp.json().get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        name = m["name"].replace("models/", "")
                        # Aggiunge il modello solo se non contiene nessuna delle keyword escluse
                        if not any(kw in name.lower() for kw in excluded_keywords):
                            models.append(ModelInfo(id=f"gemini/{name}", provider="gemini", model=name))
        except Exception as e:
            logger.warning(f"Auto-discovery Gemini fallito: {e}")

    # 3. OpenRouter (Caricato dalla lista separata da virgole nel .env)
    if settings.openrouter_api_key:
        for om in settings.parsed_openrouter_models:
            models.append(ModelInfo(id=f"openrouter/{om}", provider="openai_compatible", model=om))
            
    return models
        

@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    default_id = settings.llm_provider
    if default_id == "ollama":
        default_id = f"ollama/{settings.ollama_model}"
    elif default_id == "gemini":
        default_id = f"gemini/{settings.gemini_model}"
    elif default_id == "openrouter":
        default_id = f"openrouter/{settings.parsed_openrouter_models[0]}" if settings.parsed_openrouter_models else "openrouter/"
        
    return ModelsResponse(default=default_id, models=await _available_models())


@router.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    return [ToolInfo(name=t["name"], description=t["description"]) for t in TOOL_DESCRIPTIONS]


def _validate_request(request: QueryRequest) -> None:
    # La validazione restrittiva su llm_model è rimossa: 
    # la deleghiamo alla logica intelligente di LLMClient
    if request.allowed_tools is not None:
        unknown = set(request.allowed_tools) - set(TOOL_REGISTRY)
        if unknown:
            raise HTTPException(status_code=422, detail=f"allowed_tools sconosciuti: {sorted(unknown)}. Valori validi: {sorted(TOOL_REGISTRY)}")
        if (request.context_mode or settings.context_gathering_mode) == "none":
            raise HTTPException(status_code=422, detail="allowed_tools non ha senso con context_mode='none'")


@router.post("/query", response_model=QueryResponse)
async def query_planner(request: QueryRequest) -> QueryResponse:
    _validate_request(request)
    try:
        return await pipeline.run(request)
    except Exception as err:
        logger.exception("Errore durante l'elaborazione della richiesta planner")
        raise HTTPException(status_code=500, detail="Errore interno del planner-agent") from err


@router.post("/query/stream")
async def query_planner_stream(request: QueryRequest) -> StreamingResponse:
    _validate_request(request)

    async def event_stream() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def on_event(event: dict) -> None:
            await queue.put({"event": "progress", "data": event})

        async def worker() -> None:
            try:
                response = await pipeline.run(request, on_event)
                await queue.put({"event": "result", "data": response.model_dump(mode="json")})
            except Exception:
                logger.exception("Errore durante l'elaborazione streaming della richiesta planner")
                await queue.put({"event": "error", "data": {"message": "Errore interno del planner-agent", "timestamp": time.time()}})
            finally:
                await queue.put(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
        finally:
            task.cancel()  # se il client si disconnette a metà, non lasciamo la pipeline a girare a vuoto

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )