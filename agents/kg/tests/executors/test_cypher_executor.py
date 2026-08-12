"""
Test del guard di sola lettura del CypherExecutor.

Non richiedono un'istanza Neo4j: verificano la validazione statica della query, che è
la barriera di sicurezza fra l'output dell'llm e il database dell'utente e va quindi
testata sempre, non solo quando c'è un db attivo.
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
    # le clausole di scrittura sono anche nomi di label e di proprietà legittimi
    'MATCH (n:Set) RETURN n.name',
    'MATCH (n:Movie) RETURN n.drop',
    # la sola procedura ammessa è l'introspezione dello schema
    'CALL db.labels() YIELD label RETURN label',
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
    # l'apostrofo sfuggito chiude la stringa prima di quanto sembri: il testo che segue
    # è codice eseguito, non contenuto del letterale
    r"MATCH (n) WHERE n.p = 'a\'b' CREATE (m:Evil) RETURN 'z'",
    r"MATCH (n:Movie) RETURN n.title AS t, 'it\'s' AS x DETACH DELETE n RETURN 'end'",
    # le procedure apoc aprono transazioni proprie, che il default_access_mode non copre
    "CALL apoc.periodic.iterate('MATCH (n) RETURN n','DELETE n',{})",
    "MATCH (n) CALL apoc.create.node(['X'], {}) YIELD node RETURN node",
    # sottoquery CALL { ... }, anche con l'a capo prima della graffa
    "MATCH (n) CALL {\n  WITH n CREATE (:X)\n} RETURN n",
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
    executor = CypherExecutor(uri="bolt://localhost:7687", user="neo4j", password="password", timeout=1.0)
    with pytest.raises(CypherExecutionError):
        executor.execute("Certainly! Here is the query you asked for.")
