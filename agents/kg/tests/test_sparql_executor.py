import pytest
from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

# text che verifica se la query restituisce il risultato atteso
def test_sparql_executor():
    executor = SPARQLExecutor()

    query = """
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT ?label WHERE {
      wd:Q937 rdfs:label ?label .
      FILTER(LANG(?label) = "en")
    }
    """
    results = executor.execute(query)

    assert isinstance(results, list) # il valore restituito è una lista?
    assert len(results) > 0 # almeno un risultato
    assert results[0]["label"]["value"] == "Albert Einstein" # la query ritorna Albert Einstein?

# test che verifica la gestione degli errori
def test_sparql_executor_syntax_error():
    executor = SPARQLExecutor()
    invalid_query = "SELECT ?x WHERE { wd:Q937 " # manca la graffa di chiusura

    with pytest.raises(SPARQLExecutionError) as executor_info:
        executor.execute(invalid_query)

    assert executor_info.value.query == invalid_query
