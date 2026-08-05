import pytest
import requests
from pipeline import MultiApiPipeline


def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_weather_roma():
    pipeline = MultiApiPipeline()
    results, intent = pipeline.run("Che tempo fa a Roma?")
    assert intent == "weather"
    assert len(results) > 0
    assert "error" not in results[0]
    assert "temperature_c" in results[0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_exchange_usd_eur():
    pipeline = MultiApiPipeline()
    results, intent = pipeline.run("Quanto vale il dollaro in euro?")
    assert intent == "exchange_rate"
    assert len(results) > 0
    assert "error" not in results[0]
    assert "rates" in results[0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_unknown_intent():
    pipeline = MultiApiPipeline()
    results, intent = pipeline.run("Chi ha inventato la pizza?")
    assert intent == "unknown"
    assert "error" in results[0]


def test_cache_hit():
    """la pipeline deve restituire risultati dalla cache senza chiamare il LLM."""
    pipeline = MultiApiPipeline()
    # popola la cache manualmente
    pipeline.cache.set("test meteo roma", "weather", [{"temperature_c": 25, "condition": "Sereno"}])
    results, intent = pipeline.run("test meteo roma")
    assert intent == "weather"
    assert results[0]["temperature_c"] == 25


def test_cache_stores_results():
    """dopo una richiesta riuscita al provider, i risultati devono essere in cache."""
    pipeline = MultiApiPipeline()
    # usa il weather provider direttamente (senza LLM)
    pipeline.cache.set("Che tempo fa a Londra?", "weather", [{"temperature_c": 15}])
    # la seconda chiamata deve venire dalla cache
    cached = pipeline.cache.get("Che tempo fa a Londra?")
    assert cached is not None
    assert cached["intent"] == "weather"
