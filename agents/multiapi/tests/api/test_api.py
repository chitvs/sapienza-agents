import pytest
import requests
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "multiapi-agent"}


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query_weather():
    res = client.post("/query", json={"question": "Che tempo fa a Roma?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "weather"
    assert data["count"] > 0
    assert "temperature_c" in data["results"][0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query_exchange():
    res = client.post("/query", json={"question": "Quanto vale il dollaro in euro?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "exchange_rate"
    assert data["count"] > 0
    assert "rates" in data["results"][0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query_country():
    res = client.post("/query", json={"question": "Qual è la capitale della Francia?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "country_info"
    assert data["count"] > 0
    assert "capital" in data["results"][0]


def test_query_missing_question():
    res = client.post("/query", json={})
    assert res.status_code == 422  # validazione pydantic
