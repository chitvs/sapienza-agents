from fastapi.testclient import TestClient
from main import app
import pytest
import httpx
from configs.settings import settings

client = TestClient(app)


def llm_ready() -> bool:
    if settings.llm_provider.lower() == "gemini":
        return bool(settings.gemini_api_key)
    try:
        return httpx.get(settings.ollama_host, timeout=1).status_code == 200
    except Exception:
        return False


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "planner-agent"}


@pytest.mark.skipif(not llm_ready(), reason="Provider LLM (gemini/ollama) non disponibile")
def test_query_study_domain():
    """esempio 'esame universitario' citato nel todo."""
    res = client.post(
        "/query",
        json={"question": "Devo preparare l'esame di Reti in 3 settimane, studio 2 ore al giorno nei feriali"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["domain"] == "study"
    assert len(data["days"]) > 0
    assert "confidence" in data
    assert "execution_time_ms" in data


@pytest.mark.skipif(not llm_ready(), reason="Provider LLM (gemini/ollama) non disponibile")
def test_query_travel_domain():
    """esempio 'weekend fuori porta' citato nel todo."""
    res = client.post("/query", json={"question": "Organizzami un weekend fuori porta a Firenze"})
    assert res.status_code == 200
    data = res.json()
    assert data["domain"] == "travel"
    assert len(data["days"]) > 0


@pytest.mark.skipif(not llm_ready(), reason="Provider LLM (gemini/ollama) non disponibile")
def test_query_domain_hint_bypasses_classification():
    """domain_hint deve saltare la classificazione; il drafting resta comunque a carico del llm."""
    res = client.post("/query", json={"question": "Struttura le mie giornate lavorative", "domain_hint": "routine"})
    assert res.status_code == 200
    assert res.json()["domain"] == "routine"