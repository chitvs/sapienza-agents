"""
Centralizza la sonda di raggiungibilità del provider LLM: i test che
richiedono una risposta reale (non mockata) si marcano con
@pytest.mark.requires_llm e vengono saltati automaticamente se nessun
provider è disponibile.
"""
import httpx
import pytest

from configs.settings import settings


def _llm_ready() -> bool:
    """Verifica se un provider LLM (gemini o ollama) è raggiungibile."""
    if settings.llm_provider.lower() == "gemini":
        return bool(settings.gemini_api_key)
    try:
        return httpx.get(settings.ollama_host, timeout=1).status_code == 200
    except Exception:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _llm_ready():
        return
    skip_llm = pytest.mark.skip(reason="Provider LLM (gemini/ollama) non disponibile")
    for item in items:
        if "requires_llm" in item.keywords:
            item.add_marker(skip_llm)