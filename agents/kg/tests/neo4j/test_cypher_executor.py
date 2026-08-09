"""
Test del guard di sola lettura del CypherExecutor.

Non richiedono un'istanza Neo4j: verificano la validazione statica della query, che e'
la barriera di sicurezza fra l'output dell'llm e il database dell'utente e va quindi
testata sempre, non solo quando c'e' un db attivo.
"""
import pytest
from executors.cypher_executor import CypherExecutor, CypherExecutionError

READ_ONLY_QUERIES = [
    'MATCH (p:Person {name: "Tom Hanks"})-[:ACTED_IN]->(m:Movie) RETURN m.title',
    'MATCH (m:Movie) RETURN count(m) AS movie_count',
    'MATCH (m:Movie) WHERE toLower(m.title) CONTAINS toLower("matrix") RETURN m.title',
    'MATCH (m:Movie) RETURN m.title ORDER BY m.released DESC LIMIT 1',
    'OPTIONAL MATCH (p:Person) RETURN p.name',
    'MATCH (m:Movie) WITH m LIMIT 5 RETURN m.title',
]

WRITE_QUERIES = [
    'CREATE (p:Person {name: "x"})',
    'MATCH (p:Person) DELETE p',
    'MATCH (p:Person) DETACH DELETE p',
    'MATCH (p:Person) SET p.name = "x"',
    'MERGE (p:Person {name: "x"})',
    'MATCH (p:Person) REMOVE p.name',
    'DROP INDEX foo',
    'LOAD CSV FROM "http://example.com" AS row RETURN row',
    # tentativo di iniezione: seconda istruzione dopo il punto e virgola
    'MATCH (m:Movie) RETURN m.title; CREATE (x:Bad)',
]

@pytest.mark.parametrize("query", READ_ONLY_QUERIES)
def test_read_only_queries_are_allowed(query):
    CypherExecutor.assert_read_only(query)

@pytest.mark.parametrize("query", WRITE_QUERIES)
def test_write_queries_are_rejected(query):
    with pytest.raises(CypherExecutionError):
        CypherExecutor.assert_read_only(query)

def test_write_keyword_inside_string_literal_is_not_a_write():
    """un titolo che contiene una parola chiave di scrittura non deve bloccare la query."""
    CypherExecutor.assert_read_only('MATCH (m:Movie {title: "CREATE OR DELETE"}) RETURN m.title')

def test_conversational_hallucination_is_rejected():
    """se l'llm risponde a parole invece che con una query, l'esecuzione deve fallire subito."""
    executor = CypherExecutor()
    with pytest.raises(CypherExecutionError):
        executor.execute("Certainly! Here is the query you asked for.")
