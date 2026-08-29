"""
Client HTTP condiviso dell'applicazione.

Fornisce un singolo httpx.AsyncClient riutilizzato da llm_client.py (chiamate
a Gemini/Ollama) e da tools.py (chiamate a kg-agent/multiapi-agent), cosicché
le connessioni TCP restino aperte (keep-alive) tra una richiesta e l'altra
invece di essere aperte e chiuse ad ogni chiamata.
"""

import asyncio

import httpx

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_http_client() -> httpx.AsyncClient:
    """
    Restituisce il client HTTP condiviso, creandolo se non esiste ancora.

    Se il client esistente risulta legato a un event loop diverso da quello
    corrente (caso tipico dei test che invocano asyncio.run() più volte nello
    stesso processo), ne viene creata una nuova istanza per l'event loop
    attivo, evitando errori del tipo "attached to a different loop". Nel
    processo reale dell'app (un solo event loop uvicorn per tutta la sua
    vita) questo branch non scatta mai e il client resta un singleton vero.

    Returns:
        httpx.AsyncClient: Il client condiviso per l'event loop corrente.
    """
    global _client, _client_loop
    current_loop = asyncio.get_running_loop()

    if _client is None or _client_loop is not current_loop:
        _client = httpx.AsyncClient()
        _client_loop = current_loop

    return _client


async def close_http_client() -> None:
    """
    Chiude il client HTTP condiviso, se esiste. Va invocata allo shutdown
    dell'app (vedi lifespan in main.py) per rilasciare le connessioni aperte.
    """
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None