import pytest
from fastapi.testclient import TestClient
from main import app
from conftest import is_ollama_running

client = TestClient(app)





def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "multiapi-agent"


def test_health_espone_lo_stato_dei_provider():
    """l'healthcheck deve rendere visibile una configurazione mancante."""
    from configs.settings import settings

    providers = client.get("/health").json()["providers"]
    assert set(providers) == {"weather", "exchange_rate", "country_info", "time_info"}
    # i tre senza api key sono sempre ok
    assert providers["weather"] == providers["exchange_rate"] == providers["country_info"] == "ok"
    # il quarto deve riflettere la presenza della chiave, non dire "ok" a prescindere
    atteso = "ok" if settings.timeapi_api_key else "TIMEAPI_API_KEY mancante"
    assert providers["time_info"] == atteso


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


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_query_worldtime():
    res = client.post("/query", json={"question": "Che ore sono a Tokyo?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "time_info"
    assert data["count"] > 0
    assert "time" in data["results"][0]
    assert "timezone" in data["results"][0]

def test_query_missing_question():
    res = client.post("/query", json={})
    assert res.status_code == 422  # validazione pydantic
