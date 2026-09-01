"""
Modulo che fornisce gli strumenti (tools) per l'integrazione con agenti esterni.

Questo file contiene le funzioni client per interrogare i servizi esterni 
(come kg-agent e multiapi-agent) al fine di arricchire il contesto del piano 
con informazioni reali e aggiornate (es. meteo, entità del knowledge graph). 
Garantisce che i fallimenti di rete vengano gestiti in modo 'graceful', 
restituendo dizionari con l'errore formattato anziché sollevare eccezioni, 
per non interrompere mai la pipeline principale del Planner.
"""

import logging
from typing import Any, Awaitable, Callable

import httpx

from configs.settings import settings
from clients.http_client import get_http_client

logger = logging.getLogger("planner_tools")


async def _call_agent(base_url: str, agent_name: str, question: str) -> dict[str, Any]:
    """
    Invia una richiesta POST all'endpoint /query di un agente esterno.
    Gestisce internamente i soli fallimenti della chiamata esterna (rete/HTTP/parsing); eccezioni impreviste risalgono fino a routes.py.

    Args:
        base_url (str): L'URL di base dell'agente (es. http://localhost:8000).
        agent_name (str): Il nome dell'agente (usato per i log e i messaggi di errore).
        question (str): La domanda in linguaggio naturale da inoltrare all'agente.

    Returns:
        dict[str, Any]: Il JSON restituito dall'agente in caso di successo, oppure
        un dizionario con la chiave "error" contenente la descrizione del fallimento.
    """
    url: str = f"{base_url.rstrip('/')}/query"
    try:
        client = get_http_client()
        resp = await client.post(url, json={"question": question}, timeout=settings.external_call_timeout)
        resp.raise_for_status()
        return resp.json()
            
    except httpx.TimeoutException:
        msg: str = f"{agent_name}: timeout dopo {settings.external_call_timeout}s"
        logger.warning(f"Timeout contattando {agent_name} su {url}")
        return {"error": msg}
        
    except httpx.HTTPStatusError as err:
        msg: str = f"{agent_name}: errore HTTP {err.response.status_code}"
        logger.warning(f"Errore HTTP {err.response.status_code} da {agent_name} su {url}")
        return {"error": msg}
        
    except httpx.RequestError as err:
        # Copre errori di connessione (host irraggiungibile, connection refused, DNS, ecc.)
        msg: str = f"{agent_name}: errore di connessione ({err.__class__.__name__})"
        logger.warning(f"Errore di connessione a {agent_name} su {url}: {err}")
        return {"error": msg}

    except ValueError as err:
        # resp.json() su body 2xx ma non JSON valido: malfunzionamento dell'agente
        # esterno, non un bug interno — resta un fallimento "gestito".
        msg: str = f"{agent_name}: risposta non JSON valida ({err.__class__.__name__})"
        logger.warning(f"Risposta non valida da {agent_name} su {url}: {err}")
        return {"error": msg}


class KGAgentProvider:
    """
    Provider per l'integrazione con il Knowledge Graph Agent.
    """

    def __init__(self, base_url: str | None = None) -> None:
        """
        Inizializza il provider.
        
        Args:
            base_url (str | None): URL dell'agente. Se None, usa il default nei settings.
        """
        self.base_url: str = base_url or settings.kg_agent_url

    async def fetch(self, question: str) -> dict[str, Any]:
        """
        Inoltra la domanda al kg-agent.

        Args:
            question (str): La richiesta in linguaggio naturale.

        Returns:
            dict[str, Any]: La risposta dell'agente o il dizionario di errore.
        """
        return await _call_agent(self.base_url, "kg-agent", question)


class MultiApiProvider:
    """
    Provider per l'integrazione con il Multi-API Agent.
    """

    def __init__(self, base_url: str | None = None) -> None:
        """
        Inizializza il provider.
        
        Args:
            base_url (str | None): URL dell'agente. Se None, usa il default nei settings.
        """
        self.base_url: str = base_url or settings.multiapi_agent_url

    async def fetch(self, question: str) -> dict[str, Any]:
        """
        Inoltra la domanda al multiapi-agent.

        Args:
            question (str): La richiesta in linguaggio naturale.

        Returns:
            dict[str, Any]: La risposta dell'agente o il dizionario di errore.
        """
        return await _call_agent(self.base_url, "multiapi-agent", question)


_kg_provider = KGAgentProvider()
_multiapi_provider = MultiApiProvider()


async def query_kg(question: str) -> dict[str, Any]:
    """
    Wrapper per interrogare il Knowledge Graph. Mantenuto per compatibilità
    e per facilitare i mock nei test (es. in test_gather_context.py).

    Args:
        question (str): La sotto-domanda specifica da porre.

    Returns:
        dict[str, Any]: I risultati della ricerca o un messaggio di errore.
    """
    return await _kg_provider.fetch(question)


async def query_multiapi(question: str) -> dict[str, Any]:
    """
    Wrapper per interrogare il servizio Multi-API (meteo, valute, geo).

    Args:
        question (str): La sotto-domanda specifica da porre.

    Returns:
        dict[str, Any]: I risultati dell'API esterna o un messaggio di errore.
    """
    return await _multiapi_provider.fetch(question)


# Registro degli strumenti disponibili per il loop ReAct (Gather Context)
TOOL_REGISTRY: dict[str, Callable[[str], Awaitable[dict[str, Any]]]] = {
    "kg_agent": query_kg,
    "multiapi_agent": query_multiapi,
}

TOOL_DESCRIPTIONS: list[dict[str, Any]] = [
    {
        "name": "kg_agent",
        "description": (
            "Interroga un Knowledge Graph (Wikidata, DBpedia o un grafo Neo4j sul cinema) "
            "per estrarre fatti atomici e dati strutturati su entità specifiche. "
            "ATTENZIONE: Questo agente lavora ESCLUSIVAMENTE in lingua inglese. "
            "Qualsiasi input in altre lingue o query troppo discorsive farà fallire la ricerca."
        ),
        "parameters": {
            "tool_input": "La sotto-domanda specifica. DEVE essere secca, diretta e obbligatoriamente tradotta in INGLESE. Evita frasi discorsive o contestuali (Usa 'What is the birth date of Albert Einstein?' e NON 'Can you tell me the birth date...')."
        }
    },
    {
        "name": "multiapi_agent",
        "description": (
            "Interroga API pubbliche in tempo reale. Lavora in italiano. "
            "Supporta ESCLUSIVAMENTE 4 intenti: 1) Previsioni meteo, 2) Tassi di cambio e conversioni valuta, "
            "3) Info geografiche sulle nazioni, 4) Ora locale/fusi orari. "
            "Qualsiasi richiesta fuori da questi 4 temi produrrà un errore esplicito."
        ),
        "parameters": {
            "tool_input": "La sotto-domanda specifica in italiano (es. 'Che tempo fa a Roma domani?', 'Quanto sono 100 dollari in euro?')."
        }
    }
]