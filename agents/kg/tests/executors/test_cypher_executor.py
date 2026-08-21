"""
Test della guardia di sola lettura del CypherExecutor.
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
    'MATCH (n:Set) RETURN n.name',
    'MATCH (n:Movie) RETURN n.drop',
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
    'MATCH (m:Movie) RETURN m.title; CREATE (x:Bad)',
    r"MATCH (n) WHERE n.p = 'a\'b' CREATE (m:Evil) RETURN 'z'",
    r"MATCH (n:Movie) RETURN n.title AS t, 'it\'s' AS x DETACH DELETE n RETURN 'end'",
    "CALL apoc.periodic.iterate('MATCH (n) RETURN n','DELETE n',{})",
    "MATCH (n) CALL apoc.create.node(['X'], {}) YIELD node RETURN node",
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
    CypherExecutor.assert_read_only('MATCH (m:Movie {title: "CREATE OR DELETE"}) RETURN m.title')

def test_conversational_hallucination_is_rejected():
    executor = CypherExecutor(uri="bolt://localhost:7687", user="neo4j", password="password", timeout=1.0)
    with pytest.raises(CypherExecutionError):
        executor.execute("Certainly! Here is the query you asked for.")
