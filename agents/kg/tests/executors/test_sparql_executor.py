import pytest
from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

def test_execute():
    executor = SPARQLExecutor(timeout=30.0)
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
        if "Timeout" in str(e) or "HTTP Error" in str(e):
            pytest.skip("Wikidata SPARQL endpoint non raggiungibile")
        raise

def test_execute_syntax_error():
    executor = SPARQLExecutor(timeout=30.0)
    with pytest.raises(SPARQLExecutionError):
        executor.execute("SELECT ?x WHERE { wd:Q937 ")
