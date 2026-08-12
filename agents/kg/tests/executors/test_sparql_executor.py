import pytest
import requests

from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

def is_endpoint_reachable() -> bool:
    try:
        return requests.head("https://query.wikidata.org/sparql", timeout=3).status_code < 500
    except Exception:
        return False

@pytest.mark.skipif(not is_endpoint_reachable(), reason="endpoint SPARQL non raggiungibile")
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

def test_conversational_answer_is_rejected_locally():
    """La risposta a vuoto del modello va fermata prima della rete, non dall'endpoint."""
    # senza questo il test passerebbe anche offline, per l'errore di connessione
    executor = SPARQLExecutor(endpoint="http://invalido.localhost/sparql", timeout=1.0)
    with pytest.raises(SPARQLExecutionError, match="SYNTAX_ERROR"):
        executor.execute("Certainly! Here is the query you asked for.")

@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { wd:Q1 rdfs:label 'x' } ; SELECT ?x WHERE { ?x ?p ?o }",
        "DELETE WHERE { ?x ?p ?o } SELECT ?x WHERE { ?x ?p ?o }",
        "DROP GRAPH <http://example.org/g> SELECT ?x WHERE { ?x ?p ?o }",
        "SELECT ?x WHERE { ?x ?p ?o } LOAD <http://example.org/d>",
    ],
)
def test_update_queries_are_rejected(query):
    """L'endpoint è configurabile: su un triplestore locale scrivibile una query
    allucinata potrebbe modificare il dataset, quindi il rifiuto è nostro."""
    executor = SPARQLExecutor(endpoint="http://invalido.localhost/sparql", timeout=1.0)
    with pytest.raises(SPARQLExecutionError, match="clausola di scrittura"):
        executor.execute(query)

@pytest.mark.parametrize(
    "query",
    [
        # "Move" e "Add" qui sono risorse e variabili, non clausole di update
        "SELECT ?x WHERE { ?x rdfs:label 'Move' }",
        "SELECT ?add WHERE { ?add ?p <http://dbpedia.org/resource/Move> }",
        "SELECT ?x WHERE { ?x dbo:type dbr:Add }",
    ],
)
def test_read_only_guard_does_not_reject_valid_queries(query):
    SPARQLExecutor.assert_read_only(query)
