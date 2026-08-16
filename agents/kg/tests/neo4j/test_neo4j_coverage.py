"""
Copertura estesa della pipeline Neo4j sul movie graph.
"""

import pytest
from pipeline import KGPipeline
from conftest import contains_answer, is_neo4j_ready, is_ollama_running

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_neo4j_ready()),
    reason="richiede Ollama attivo e Neo4j con il movie graph caricato",
)

@pytest.fixture(scope="module")
def pipeline() -> KGPipeline:
    return KGPipeline(target_kg="neo4j")

@requires_stack
def test_writer_relationship(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who wrote A Few Good Men?")
    assert len(result.results) > 0
    assert contains_answer(result, "Sorkin")

@requires_stack
def test_producer_relationship(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who produced The Matrix?")
    assert len(result.results) > 0
    assert contains_answer(result, "Silver")

@requires_stack
def test_person_to_person_relationship(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who follows Jessica Thompson?")
    assert len(result.results) > 0
    assert contains_answer(result, "Thompson") or contains_answer(result, "Scope")

@requires_stack
def test_relationship_property(pipeline: KGPipeline) -> None:
    result = pipeline.run("What rating did Jessica Thompson give to The Replacements?")
    assert len(result.results) > 0

@requires_stack
def test_roles_property_on_relationship(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which role did Keanu Reeves play in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_numeric_range_filter(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which movies were released before 1995?")
    assert len(result.results) > 0

@requires_stack
def test_person_born_after_year(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which people were born after 1970?")
    assert len(result.results) > 0

@requires_stack
def test_three_level_chain(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who directed the movies that Tom Hanks acted in?")
    assert len(result.results) > 0

@requires_stack
def test_count_distinct_people(pipeline: KGPipeline) -> None:
    result = pipeline.run("How many people acted in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_ambiguous_title_prefix(pipeline: KGPipeline) -> None:
    result = pipeline.run("When was The Matrix released?")
    assert len(result.results) > 0
    assert contains_answer(result, "1999")

@requires_stack
def test_person_who_both_acted_and_directed(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which people both acted in and directed a movie?")
    assert "MATCH" in result.query.upper()

@requires_stack
def test_movie_with_most_actors(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which movie has the most actors?")
    assert len(result.results) > 0

@requires_stack
def test_tagline_property(pipeline: KGPipeline) -> None:
    result = pipeline.run("What is the tagline of The Matrix?")
    assert len(result.results) > 0
