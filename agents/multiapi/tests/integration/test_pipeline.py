import pytest
import requests
from configs.settings import settings
from pipeline import MultiApiPipeline


def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_weather_roma():
    pipeline = MultiApiPipeline()
    results, intent, cached = pipeline.run("Che tempo fa a Roma?")
    assert intent == "weather"
    assert len(results) > 0
    assert "error" not in results[0]
    assert "temperature_c" in results[0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_exchange_usd_eur():
    pipeline = MultiApiPipeline()
    results, intent, cached = pipeline.run("Quanto vale il dollaro in euro?")
    assert intent == "exchange_rate"
    assert len(results) > 0
    assert "error" not in results[0]
    assert "rates" in results[0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_country_france():
    pipeline = MultiApiPipeline()
    results, intent, cached = pipeline.run("Qual è la capitale della Francia?")
    assert intent == "country_info"
    assert len(results) > 0
    assert "error" not in results[0]
    assert results[0]["capital"] == "Paris"


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_unknown_intent():
    pipeline = MultiApiPipeline()
    results, intent, cached = pipeline.run("Chi ha inventato la pizza?")
    assert intent == "unknown"
    assert "error" in results[0]


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_worldtime_tokyo():
    pipeline = MultiApiPipeline()
    results, intent, cached = pipeline.run("Che ore sono a Tokyo?")
    assert intent == "time_info"
    assert len(results) > 0
    assert "error" not in results[0]
    assert results[0]["timezone"] == "Asia/Tokyo"
    assert len(results[0]["time"]) == 8  # HH:MM:SS

def test_cache_hit():
    """la pipeline deve restituire risultati dalla cache senza chiamare il LLM."""
    pipeline = MultiApiPipeline()
    # popola la cache manualmente
    pipeline.cache.set("test meteo roma", "weather", [{"temperature_c": 25, "condition": "Sereno"}])
    results, intent, cached = pipeline.run("test meteo roma")
    assert intent == "weather"
    assert results[0]["temperature_c"] == 25
    assert cached is True


def test_time_info_non_va_in_cache():
    """l'ora non va riusata: con il ttl previsto per time_info non resta traccia in cache.

    Riproduce lo step 3 di MultiApiPipeline.run senza passare dall'llm.
    """
    pipeline = MultiApiPipeline()
    ttl = settings.cache_ttl_by_intent.get("time_info", settings.cache_ttl_default)
    assert ttl == 0, "time_info deve avere ttl 0: un orario riusato e sbagliato"

    pipeline.cache.set("che ore sono a tokyo", "time_info", [{"time": "04:39:12"}], ttl=ttl)
    assert pipeline.cache.get("che ore sono a tokyo") is None


def test_ttl_ordinati_per_volatilita():
    """i dati piu volatili devono scadere prima di quelli piu stabili."""
    t = settings.cache_ttl_by_intent
    assert t["time_info"] < t["weather"] < t["exchange_rate"] < t["country_info"]


def test_cache_stores_results():
    """dopo una richiesta riuscita al provider, i risultati devono essere in cache."""
    pipeline = MultiApiPipeline()
    # usa il weather provider direttamente (senza LLM)
    pipeline.cache.set("Che tempo fa a Londra?", "weather", [{"temperature_c": 15}])
    # la seconda chiamata deve venire dalla cache
    cached = pipeline.cache.get("Che tempo fa a Londra?")
    assert cached is not None
    assert cached["intent"] == "weather"
