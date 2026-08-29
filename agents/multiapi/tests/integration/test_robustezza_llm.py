"""
Robustezza della pipeline rispetto a risposte malformate del modello.

Nessuna rete e nessun llm: _llm_generate viene sostituito da una funzione che
restituisce la stringa voluta. json.loads accetta anche array e scalari, che gli
estrattori non possono usare perché accedono ai campi per chiave.
"""

import pytest

from pipeline import MultiApiPipeline

MALFORMATE = [
    ("array json", '[{"city": "Roma"}]'),
    ("stringa json", '"Roma"'),
    ("numero json", "42"),
    ("null json", "null"),
    ("booleano json", "true"),
    ("testo libero", "La citta e Roma"),
    ("risposta vuota", ""),
    ("json troncato", '{"city": "Rom'),
]


def pipeline_che_risponde(testo: str) -> MultiApiPipeline:
    p = MultiApiPipeline()
    p.corrector.max_retries = 0  # isola il comportamento senza retry
    p._llm_generate = lambda prompt, temperature=0.0: testo
    return p


@pytest.mark.parametrize("etichetta,risposta", MALFORMATE)
def test_estrattori_non_sollevano_eccezioni(etichetta, risposta):
    p = pipeline_che_risponde(risposta)
    assert p._extract_weather_params("Che tempo fa a Roma?")["city"] is None
    assert p._extract_country("parlami dell Italia") is None
    assert p._extract_timezone_city("che ore sono a Tokyo") is None
    assert p._extract_exchange_params("cambio euro dollaro")["from_currency"] is None


@pytest.mark.parametrize("etichetta,risposta", MALFORMATE)
def test_classificazione_ricade_su_unknown(etichetta, risposta):
    p = pipeline_che_risponde(risposta)
    intent, altri = p._classify_intent("Che tempo fa a Roma?")
    assert intent == "unknown"
    assert altri == []


@pytest.mark.parametrize("etichetta,risposta", MALFORMATE)
def test_run_completo_degrada_senza_500(etichetta, risposta):
    """la richiesta deve chiudersi con un errore, non con un'eccezione."""
    p = pipeline_che_risponde(risposta)
    results, intent, cached, ignorati = p.run("Che tempo fa a Roma?")
    assert intent == "unknown"
    assert "error" in results[0]
    assert cached is False


def test_other_intents_malformato_viene_ignorato():
    """other_intents può contenere etichette non previste o duplicate."""
    p = pipeline_che_risponde('{"intent": "weather", "other_intents": "time_info"}')
    assert p._classify_intent("x") == ("weather", [])

    p = pipeline_che_risponde('{"intent": "weather", "other_intents": ["weather", "sport", "time_info"]}')
    intent, altri = p._classify_intent("x")
    assert intent == "weather"
    assert altri == ["time_info"], "si tengono solo intent noti e diversi dal principale"


def test_il_corrector_scatta_e_recupera():
    """dopo una risposta inutilizzabile, un secondo tentativo valido va accettato."""
    p = MultiApiPipeline()
    risposte = iter(['[1, 2, 3]', '{"city": "Roma", "days_ahead": null}'])
    p._llm_generate = lambda prompt, temperature=0.0: next(risposte)
    assert p._extract_weather_params("Che tempo fa a Roma?")["city"] == "Roma"
