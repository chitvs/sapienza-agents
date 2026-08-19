"""
Test sulle API di ricerca e sull'endpoint SPARQL di Wikidata.
"""

import pytest
from conftest import is_wikidata_endpoint_reachable, is_wikidata_reachable
from connectors.wikidata_connector import WikidataConnector
from executors.sparql_executor import SPARQLExecutionError, SPARQLExecutor

needs_wikidata = pytest.mark.skipif(not is_wikidata_reachable(), reason="Wikidata non raggiungibile")
needs_endpoint = pytest.mark.skipif(
    not is_wikidata_endpoint_reachable(), reason="endpoint SPARQL non raggiungibile"
)

@needs_wikidata
def test_search_entity():
    connector = WikidataConnector()
    results = connector.search_entity("universe", limit=5)
    assert len(results) > 0
    assert any(r.id == "Q1" for r in results)

@needs_wikidata
def test_get_entity():
    connector = WikidataConnector()
    entity = connector.get_entity("Q1")
    assert entity.id == "Q1"
    assert entity.label != ""

@needs_wikidata
def test_ground_results():
    connector = WikidataConnector()
    grounded = connector.ground_results([{"person": "http://www.wikidata.org/entity/Q937"}])
    assert len(grounded) == 1
    assert "Albert Einstein" in grounded[0]["person"]

@needs_wikidata
def test_ground_results_keeps_source_uri():
    connector = WikidataConnector()
    raw = [{"item": {"value": "http://www.wikidata.org/entity/Q937"},
            "date": {"value": "+1879-03-14T00:00:00Z"}}]
    grounded = connector.ground_results(raw)[0]
    assert grounded["item"] == "Albert Einstein"
    assert grounded["_sources"]["item"] == "http://www.wikidata.org/entity/Q937"
    assert "date" not in grounded["_sources"]

@needs_endpoint
def test_execute():
    executor = SPARQLExecutor(endpoint="https://query.wikidata.org/sparql", timeout=30.0)
    query = """
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?label WHERE {
      wd:Q937 rdfs:label ?label .
      FILTER(LANG(?label) = "en")
    }
    """
    try:
        results = executor.execute(query)
        assert len(results) > 0
        assert results[0]["label"]["value"] == "Albert Einstein"
    except SPARQLExecutionError as e:
        if e.retryable:
            pytest.skip("endpoint SPARQL non raggiungibile o in errore transitorio")
        raise
