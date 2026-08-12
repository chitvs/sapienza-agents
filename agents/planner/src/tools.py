"""
Tool deterministici per il recupero di contesto esterno (Step 5 della roadmap planner).

Funzioni async pure, nessun decoratore/tipo LangChain: il dispatch verso questi tool è
deciso a monte da pipeline._gather_context in base al dominio già classificato in Fase 1,
non dall'LLM (zero chiamate LLM aggiuntive per "decidere quali strumenti usare").

Contratto: ogni funzione restituisce sempre un dict - la risposta grezza dell'agente in
caso di successo, oppure {"error": "<descrizione specifica del fallimento>"} in caso di
fallimento - mai un'eccezione propagata al chiamante. Nessun fallimento di rete deve far
crashare la pipeline.
"""

import httpx

from configs.settings import settings
from typing import Callable, Awaitable


async def _call_agent(base_url: str, agent_name: str, question: str) -> dict:
    """POST {base_url}/query con {"question": question}; mai un'eccezione propagata."""
    url = f"{base_url.rstrip('/')}/query"
    try:
        async with httpx.AsyncClient(timeout=settings.external_call_timeout) as client:
            resp = await client.post(url, json={"question": question})
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        return {"error": f"{agent_name}: timeout dopo {settings.external_call_timeout}s"}
    except httpx.HTTPStatusError as err:
        return {"error": f"{agent_name}: errore HTTP {err.response.status_code}"}
    except httpx.RequestError as err:
        # copre errori di connessione (host irraggiungibile, connection refused, DNS, ecc.)
        return {"error": f"{agent_name}: errore di connessione ({err.__class__.__name__})"}
    except Exception as err:  # rete di sicurezza: mai far propagare un'eccezione imprevista
        return {"error": f"{agent_name}: errore imprevisto ({err.__class__.__name__})"}


async def query_kg(question: str) -> dict:
    """interroga kg-agent (POST {settings.kg_agent_url}/query)."""
    return await _call_agent(settings.kg_agent_url, "kg-agent", question)


async def query_multiapi(question: str) -> dict:
    """interroga multiapi-agent (POST {settings.multiapi_agent_url}/query)."""
    return await _call_agent(settings.multiapi_agent_url, "multiapi-agent", question)

TOOL_REGISTRY: dict[str, Callable[[str], Awaitable[dict]]] = {
    "kg_agent": query_kg,
    "multiapi_agent": query_multiapi,
}

TOOL_DESCRIPTIONS = [
    {
        "name": "kg_agent",
        "description": (
            "Interroga il Knowledge Graph per ottenere fatti e informazioni strutturate "
            "su entità specifiche (es. luoghi storici, persone, monumenti, concetti accademici)."
        ),
        "parameters": {
            "tool_input": "La sotto-domanda specifica e mirata da porre in linguaggio naturale."
        }
    },
    {
        "name": "multiapi_agent",
        "description": (
            "Interroga API esterne in tempo reale. Usa questo tool ESCLUSIVAMENTE per: "
            "1) Previsioni meteo. 2) Tassi di cambio. 3) Info geografiche base sui paesi."
        ),
        "parameters": {
            "tool_input": "La sotto-domanda specifica e mirata da porre in linguaggio naturale."
        }
    }
]