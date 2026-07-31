import pytest
import requests
from translators.sparql_translator import SPARQLTranslator

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_sanitize_sparql_variable_spaces():
    query = "SELECT ? var WHERE { wd:Q937 wdt:P569 ? var . }"
    sanitized = SPARQLTranslator.sanitize_sparql(query)
    assert "?var" in sanitized

def test_sanitize_sparql_service_outside_where():
    query = "SELECT ?label WHERE { wd:Q937 rdfs:label ?label . } SERVICE wikibase:label { bd:serviceParam wikibase:language 'en'. }"
    sanitized = SPARQLTranslator.sanitize_sparql(query)
    assert "SERVICE wikibase:label" in sanitized
    assert sanitized.endswith("}")

def test_sanitize_sparql_aggregate_alias():
    query = "SELECT COUNT(?item) WHERE { wd:Q937 wdt:P31 ?item . }"
    sanitized = SPARQLTranslator.sanitize_sparql(query)
    assert "AS ?count" in sanitized

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate():
    translator = SPARQLTranslator()
    query = translator.translate(
        question="Qual è la data di nascita di Albert Einstein?",
        schema_context="Albert Einstein (wd:Q937), data di nascita (wdt:P569)",
    )
    assert "SELECT" in query.upper()
    assert "wd:Q937" in query
