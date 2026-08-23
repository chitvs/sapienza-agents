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


def _available_models() -> list[ModelInfo]:
    models = [ModelInfo(id="ollama", provider="ollama", model=settings.ollama_model)]
    if settings.gemini_api_key:
        models.append(ModelInfo(id="gemini", provider="gemini", model=settings.gemini_model))
    for name, cfg in settings.openai_providers.items():
        if cfg.get("base_url") and cfg.get("model"):
            models.append(ModelInfo(id=name, provider="openai_compatible", model=cfg["model"]))
    return models


@router.get("/models", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    return ModelsResponse(default=settings.llm_provider, models=_available_models())


@router.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    return [ToolInfo(name=t["name"], description=t["description"]) for t in TOOL_DESCRIPTIONS]


def _validate_request(request: QueryRequest) -> None:
    if request.llm_model is not None:
        valid_ids = {m.id for m in _available_models()}
        if request.llm_model not in valid_ids:
            raise HTTPException(status_code=422, detail=f"llm_model sconosciuto: {request.llm_model!r}. Valori validi: {sorted(valid_ids)}")
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