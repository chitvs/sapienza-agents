import pytest
import requests
from translators.sparql_translator import SPARQLTranslator

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_sanitize_sparql_aggregations():
    translator = SPARQLTranslator.__new__(SPARQLTranslator)
    raw = "SELECT COUNT (?item) WHERE { wd:Q458 wdt:P527 ?item . }"
    sanitized = translator.sanitize_sparql(raw)
    assert "SELECT (COUNT(?item) AS ?count) WHERE" in sanitized

    raw_distinct = "SELECT COUNT ( DISTINCT ?item ) WHERE { wd:Q458 wdt:P527 ?item . }"
    sanitized_distinct = translator.sanitize_sparql(raw_distinct)
    assert "COUNT(DISTINCT ?item)" in sanitized_distinct or "COUNT( DISTINCT ?item )" in sanitized_distinct

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate_count_query():
    translator = SPARQLTranslator()
    schema_ctx = "entità: wd:Q458 (European Union)\nproprietà: [wdt:P527 [P527 (has part or member)] (valori: ['Q142', 'Q183'])]"
    query = translator.translate("Quanti paesi fanno parte dell'Unione Europea?", schema_context=schema_ctx)
    assert "COUNT" in query.upper()
    assert "Q458" in query
    assert "P527" in query

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate_multi_hop_query():
    translator = SPARQLTranslator()
    schema_ctx = "entità: wd:Q937 (Albert Einstein)\nproprietà: [wdt:P26 [P26 (spouse)] (valori: ['Q158097']), wdt:P19 [P19 (place of birth)] (valori: ['Q3012'])]"
    query = translator.translate("In quale città è nata la moglie di Albert Einstein?", schema_context=schema_ctx)
    assert "Q937" in query
    assert "P26" in query
    assert "P19" in query or "spouse" in query.lower()

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate_temporal_qualifier_query():
    translator = SPARQLTranslator()
    schema_ctx = "entità: wd:Q8682 (Real Madrid CF)\nproprietà: [p:P488 [P488 (chairperson)] (valori: ['Q245207']), pq:P580 [P580 (start time)] (valori: ['2009-06-01'])]"
    query = translator.translate("Chi è stato presidente del Real Madrid a partire dal 2009?", schema_context=schema_ctx)
    assert "Q8682" in query
    assert "P488" in query
