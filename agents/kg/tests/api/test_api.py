from fastapi.testclient import TestClient
from main import app
import pytest
import requests

client = TestClient(app)

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "kg-agent"}

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query():
    res = client.post("/query", json={"question": "Qual è la data di nascita di Albert Einstein?"})
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert "1879-03-14" in str(data["results"][0])
