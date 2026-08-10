import pytest
import requests

from connectors.wikidata_connector import WikidataConnector
from translators.sparql_translator import WikidataSPARQLTranslator as SPARQLTranslator

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_ask_query_survives_sanitize_and_postprocess():
    """
    Una ASK non ha proiezione: le euristiche pensate per la SELECT non devono toccarla, o
    trasformerebbero una domanda sì/no in qualcos'altro.
    """
    query = "ASK { wd:Q37767 wdt:P166 wd:Q37922. }"
    translator = SPARQLTranslator.__new__(SPARQLTranslator)
    assert translator.postprocess(SPARQLTranslator.sanitize(query), "Did he win?") == query

def test_ask_boolean_is_not_turned_into_a_string():
    """Il booleano di una ASK deve restare un booleano: "false" è una risposta, non un testo."""
    grounded = WikidataConnector().ground_results([{"boolean": False}])
    assert grounded == [{"boolean": False}]

def test_sanitize_variable_spaces():
    query = "SELECT ? var WHERE { wd:Q937 wdt:P569 ? var . }"
    sanitized = SPARQLTranslator.sanitize(query)
    assert "?var" in sanitized

def test_sanitize_service_outside_where():
    query = "SELECT ?label WHERE { wd:Q937 rdfs:label ?label . } SERVICE wikibase:label { bd:serviceParam wikibase:language 'en'. }"
    sanitized = SPARQLTranslator.sanitize(query)
    assert "SERVICE wikibase:label" in sanitized
    assert sanitized.endswith("}")

def test_sanitize_aggregate_alias():
    query = "SELECT COUNT(?item) WHERE { wd:Q937 wdt:P31 ?item . }"
    sanitized = SPARQLTranslator.sanitize(query)
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
