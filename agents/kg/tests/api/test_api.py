from fastapi.testclient import TestClient
from main import app
import pytest
from conftest import is_ollama_running

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "kg-agent"}

def test_unsupported_kg_is_rejected():
    res = client.post("/query", json={"question": "x", "target_kg": "yago"})
    assert res.status_code == 400
    assert "yago" in res.json()["detail"]

def test_missing_prerequisite_explains_itself(monkeypatch):
    """
    L'indice FAISS è un artefatto di build: se manca, il messaggio che spiega come generarlo
    deve arrivare al client. Il codice è 500 e non 503, perché è un guasto nostro e non del
    knowledge graph, che invece è perfettamente raggiungibile.
    """
    import api.routes as routes

    def build_fallito(*args, **kwargs):
        raise FileNotFoundError("Indice FAISS delle proprietà non trovato. Eseguire 'python scripts/ingest_wikidata.py'.")

    monkeypatch.setattr(routes, "KGPipeline", build_fallito)
    monkeypatch.setattr(routes, "_pipelines", {})

    res = client.post("/query", json={"question": "x", "target_kg": "wikidata"})
    assert res.status_code == 500
    assert "ingest_wikidata.py" in res.json()["detail"]

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query():
    res = client.post("/query", json={"question": "What is the birth date of Albert Einstein?"})
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert "confidence" in data
    assert 0.0 < data["confidence"] <= 1.0
    assert "execution_time_ms" in data
    assert data["execution_time_ms"] > 0
    assert "1879-03-14" in str(data["results"][0])
