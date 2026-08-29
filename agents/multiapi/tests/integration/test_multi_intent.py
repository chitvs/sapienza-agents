"""
Domande che citano più temi: la pipeline serve un ramo per ciascuno, entro il
tetto configurato. Nessuna rete e nessun llm.
"""

import pytest

from configs.settings import settings
from pipeline import MultiApiPipeline


def pipeline_finta(intent, altri):
    """pipeline con classificazione e provider sostituiti da valori fissi."""
    p = MultiApiPipeline()
    p._classify_intent = lambda q: (intent, altri)
    p._run_weather = lambda q: [{"kind": "current", "city": "Roma", "condition": "Sereno", "temperature_c": 30.0}]
    p._run_worldtime = lambda q: [{"city": "Roma", "time": "12:00:00", "date": "2026-08-24", "timezone": "Europe/Rome"}]
    p._run_exchange = lambda q: [{"base": "EUR", "quote": "USD", "rates": 1.17, "amount": 1.0, "date": "2026-08-24"}]
    p._run_country = lambda q: [{"name": "Italy", "capital": "Rome"}]
    return p


def test_due_intent_danno_due_risultati():
    p = pipeline_finta("weather", ["time_info"])
    results, intent, cached, ignorati = p.run("Che tempo fa a Roma e che ore sono?")
    assert len(results) == 2
    assert intent == "weather", "l'intent di primo livello resta il principale"
    assert ignorati == [], "un intent servito non è più ignorato"


def test_ogni_risultato_dichiara_il_proprio_intent():
    """senza questo campo l'interfaccia non saprebbe quale card usare per ciascuno."""
    p = pipeline_finta("weather", ["time_info"])
    results, _, _, _ = p.run("Che tempo fa a Roma e che ore sono?")
    assert [r["intent"] for r in results] == ["weather", "time_info"]


def test_ogni_risultato_ha_la_sua_sintesi():
    p = pipeline_finta("weather", ["time_info"])
    results, _, _, _ = p.run("domanda")
    assert "Meteo attuale" in results[0]["summary"]
    assert "sono le 12:00:00" in results[1]["summary"]


def test_il_tetto_limita_gli_intent_serviti():
    p = pipeline_finta("weather", ["time_info", "exchange_rate", "country_info"])
    results, _, _, ignorati = p.run("domanda")
    assert len(results) == settings.max_intents_per_question
    # quelli oltre il tetto restano dichiarati come non trattati
    assert ignorati == ["exchange_rate", "country_info"]


def test_un_solo_intent_si_comporta_come_prima():
    p = pipeline_finta("weather", [])
    results, intent, cached, ignorati = p.run("Che tempo fa a Roma?")
    assert len(results) == 1
    assert intent == "weather"
    assert ignorati == []


def test_ttl_e_il_minimo_fra_gli_intent_serviti():
    """con time_info fra i temi la risposta non va in cache: l'ora sarebbe stantia."""
    p = pipeline_finta("weather", ["time_info"])
    p.run("Che tempo fa a Roma e che ore sono?")
    assert p.cache.get("Che tempo fa a Roma e che ore sono?") is None


def test_senza_intent_volatili_la_risposta_e_memorizzata():
    p = pipeline_finta("weather", ["country_info"])
    p.run("Che tempo fa a Roma e parlami dell'Italia")
    assert p.cache.get("Che tempo fa a Roma e parlami dell'Italia") is not None


def test_un_ramo_fallito_non_impedisce_la_cache_degli_altri():
    """se un intent fallisce, la risposta mista non va in cache."""
    p = pipeline_finta("weather", ["country_info"])
    p._run_country = lambda q: [{"error": "paese non trovato"}]
    results, _, _, _ = p.run("domanda mista")
    assert len(results) == 2
    assert p.cache.get("domanda mista") is None


def test_intent_sconosciuto_resta_un_errore():
    p = pipeline_finta("unknown", [])
    results, intent, _, _ = p.run("Chi ha inventato la pizza?")
    assert intent == "unknown"
    assert "error" in results[0]
