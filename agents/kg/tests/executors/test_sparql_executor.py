import pytest

from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

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
