"""
Test di integrazione end-to-end su Neo4j.
"""

import pytest
from configs.settings import settings
from executors.cypher_executor import CypherExecutor, CypherExecutionError
from pipeline import KGPipeline
from conftest import contains_answer, is_neo4j_ready, is_ollama_running

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_neo4j_ready()),
    reason="richiede Ollama attivo e Neo4j con il movie graph caricato (scripts/setup_neo4j_movies.py)",
)

@pytest.fixture(scope="module")
def pipeline():
    return KGPipeline(target_kg="neo4j")

@requires_stack
def test_movies_acted_in_by_person(pipeline):
    result = pipeline.run("Which movies did Tom Hanks act in?")
    assert len(result.results) > 0
    assert contains_answer(result, "Apollo 13") or contains_answer(result, "Forrest Gump")

@requires_stack
def test_director_of_movie(pipeline):
    result = pipeline.run("Who directed The Matrix?")
    assert len(result.results) > 0
    assert contains_answer(result, "Wachowski")

@requires_stack
def test_co_actors_two_hops(pipeline):
    result = pipeline.run("Which actors worked with Keanu Reeves?")
    assert len(result.results) > 0

@requires_stack
def test_count_aggregation(pipeline):
    result = pipeline.run("How many movies did Tom Hanks act in?")
    assert len(result.results) > 0

@requires_stack
def test_superlative_most_recent(pipeline):
    result = pipeline.run("What is the most recent movie in the graph?")
    assert len(result.results) > 0

@requires_stack
def test_destructive_question_never_modifies_the_graph(pipeline):
    counter = CypherExecutor(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
        timeout=10.0,
    )
    count_query = "MATCH (n) RETURN count(n) AS c"
    before = counter.execute_trusted(count_query, {})[0]["c"]

    try:
        result = pipeline.run("Delete all movies from the database")
        if result.query:
            CypherExecutor.assert_read_only(result.query)
    except CypherExecutionError:
        pass

    after = counter.execute_trusted(count_query, {})[0]["c"]
    counter.close()

    assert after == before, f"il grafo è stato modificato: {before} nodi prima, {after} dopo"
