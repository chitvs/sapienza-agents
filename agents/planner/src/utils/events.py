"""
Eventi di avanzamento emessi da PlannerPipeline/ContextGatherer durante
l'elaborazione di una richiesta.

Consumati dall'endpoint di streaming (api/routes.py), che li inoltra al
client come Server-Sent Events. Gli status sono centralizzati in EventStatus
invece di essere stringhe libere sparse nel codice: un refuso in una stringa
diventerebbe altrimenti un evento silenziosamente perso lato frontend.
"""

import time
from enum import Enum
from typing import Any, Awaitable, Callable


class EventStatus(str, Enum):
    """Stadi di avanzamento della pipeline, riportati via SSE."""

    STARTED = "started"
    CLASSIFYING_DOMAIN = "classifying_domain"
    DOMAIN_CLASSIFIED = "domain_classified"
    GATHERING_CONTEXT = "gathering_context"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    DRAFTING = "drafting"
    VALIDATING = "validating"
    CORRECTING = "correcting"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


async def emit(on_event: EventCallback | None, status: EventStatus, message: str, **extra: Any) -> None:
    """Notifica un evento di avanzamento al chiamante. No-op se on_event è None
    (percorso non-streaming, /query).

    Args:
        on_event: La callback a cui notificare l'evento, o None.
        status: Lo stadio di avanzamento raggiunto.
        message: Un messaggio leggibile da mostrare all'utente.
        **extra: Campi aggiuntivi specifici dell'evento (es. tool, domain).
    """
    if on_event is None:
        return
    await on_event({"status": status.value, "message": message, "timestamp": time.time(), **extra})


async def run_tracked_tool(on_event: EventCallback | None, name: str, coro: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Esegue una chiamata tool emettendo tool_started/tool_completed.

    Il chiamante crea la coroutine (es. query_kg(...)) senza awaitarla: così
    più chiamate restano eseguibili in parallelo con asyncio.gather anche
    passando da qui.

    Args:
        on_event: La callback a cui notificare gli eventi, o None.
        name: Il nome del tool (per il campo 'tool' degli eventi).
        coro: La coroutine, non ancora awaitata, che esegue la chiamata.

    Returns:
        Il risultato del tool: il dizionario di successo, oppure uno con
        chiave 'error' se la chiamata è fallita.
    """
    await emit(on_event, EventStatus.TOOL_STARTED, f"Chiamata a {name}", tool=name)
    start = time.time()
    result = await coro
    duration_ms = round((time.time() - start) * 1000, 2)

    # 'tool_status', non 'status': quest'ultima è già la chiave fissa dello
    # stage-name dentro emit(); un kwarg extra con lo stesso nome la
    # sovrascriverebbe silenziosamente.
    if "error" in result:
        await emit(on_event, EventStatus.TOOL_COMPLETED, f"{name} fallito", tool=name, duration_ms=duration_ms, tool_status="error", error=result["error"])
    else:
        await emit(on_event, EventStatus.TOOL_COMPLETED, f"{name} completato", tool=name, duration_ms=duration_ms, tool_status="ok")
    return result