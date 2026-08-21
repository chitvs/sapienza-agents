"""
Test del traduttore SPARQL.
"""

import pytest
from connectors.wikidata_connector import WikidataConnector
from translators.sparql_translator import WikidataSPARQLTranslator as SPARQLTranslator
from conftest import is_ollama_running

def test_ask_query_survives_sanitize_and_postprocess():
    query = "ASK { wd:Q37767 wdt:P166 wd:Q37922. }"
    translator = SPARQLTranslator.__new__(SPARQLTranslator)
    assert translator.postprocess(SPARQLTranslator.sanitize(query), "Did he win?") == query

def test_ask_boolean_is_not_turned_into_a_string():
    grounded = WikidataConnector().ground_results([{"boolean": False}])
    assert grounded == [{"boolean": False}]

def test_sanitize_variable_spaces():
    query = "SELECT ? var WHERE { wd:Q937 wdt:P569 ? var . }"
    sanitized = SPARQLTranslator.sanitize(query)
    assert "?var" in sanitized

def test_sanitize_service_outside_where():
    query = "SELECT ?label WHERE { wd:Q937 rdfs:label ?label . } SERVICE wikibase:label { bd:serviceParam wikibase:language 'en'. }"
    sanitized = SPARQLTranslator.sanitize(query)
    opening, closing = SPARQLTranslator._where_span(sanitized)
    assert opening < sanitized.index("SERVICE wikibase:label") < closing

def test_sanitize_leaves_service_already_inside_where():
    query = (
        "SELECT ?x ?xLabel WHERE { { ?x wdt:P27 wd:Q30 } UNION { ?x wdt:P27 wd:Q145 }\n"
        "  SERVICE wikibase:label { bd:serviceParam wikibase:language 'en'. }\n}"
    )
    sanitized = SPARQLTranslator.sanitize(query)
    assert "wd:Q145 }" in sanitized
    assert sanitized.count("SERVICE wikibase:label") == 1

def test_sanitize_preserves_string_literals():
    query = 'SELECT ?x WHERE { ?x rdfs:label ?l . FILTER(CONTAINS(?l, "What? Really")) }'
    assert '"What? Really"' in SPARQLTranslator.sanitize(query)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate():
    translator = SPARQLTranslator()
    query = translator.translate(
        question="Qual è la data di nascita di Albert Einstein?",
        schema_context="Albert Einstein (wd:Q937), data di nascita (wdt:P569)",
    )
    assert "SELECT" in query.upper()
    assert "wd:Q937" in query
