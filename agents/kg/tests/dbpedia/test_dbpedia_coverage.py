"""
Copertura estesa della pipeline DBpedia.
"""

from pathlib import Path
import pytest
from pipeline import KGPipeline
from conftest import contains_answer, is_dbpedia_reachable, is_ollama_running

_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "dbpedia_ontology"

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_dbpedia_reachable() and (_INDEX_DIR / "properties.faiss").exists()),
    reason="richiede Ollama, l'endpoint DBpedia e l'indice ontologico (scripts/ingest_dbpedia.py)",
)

@pytest.fixture(scope="module")
def pipeline() -> KGPipeline:
    return KGPipeline(target_kg="dbpedia")

@requires_stack
def test_inverse_relation(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which films were directed by Christopher Nolan?")
    assert len(result.results) > 0

@requires_stack
def test_resource_with_parentheses_in_uri(pipeline: KGPipeline) -> None:
    result = pipeline.run("What is the mass of the planet Mercury?")
    assert "dbr:Mercury_(planet)" not in result.query

@requires_stack
def test_superlative_with_type_filter(pipeline: KGPipeline) -> None:
    result = pipeline.run("What is the highest mountain?")
    assert len(result.results) > 0

@requires_stack
def test_date_property(pipeline: KGPipeline) -> None:
    result = pipeline.run("When was Albert Einstein born?")
    assert len(result.results) > 0
    assert contains_answer(result, "1879")

@requires_stack
def test_death_place(pipeline: KGPipeline) -> None:
    result = pipeline.run("Where did Albert Einstein die?")
    assert len(result.results) > 0
    assert contains_answer(result, "Princeton")

@requires_stack
def test_multi_valued_property(pipeline: KGPipeline) -> None:
    result = pipeline.run("Which actors starred in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_three_hop_chain(pipeline: KGPipeline) -> None:
    result = pipeline.run("In which country was the director of Inception born?")
    assert "SELECT" in result.query.upper()

@requires_stack
def test_spouse_relation(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who was the spouse of Albert Einstein?")
    assert "SELECT" in result.query.upper()

@requires_stack
def test_count_with_inverse_relation(pipeline: KGPipeline) -> None:
    result = pipeline.run("How many films did Steven Spielberg direct?")
    assert len(result.results) > 0

@requires_stack
def test_country_population(pipeline: KGPipeline) -> None:
    result = pipeline.run("What is the population of Italy?")
    assert len(result.results) > 0

@requires_stack
def test_ambiguous_entity_name(pipeline: KGPipeline) -> None:
    result = pipeline.run("Who was the lead singer of Queen?")
    assert "SELECT" in result.query.upper()

@requires_stack
def test_film_numeric_property(pipeline: KGPipeline) -> None:
    result = pipeline.run("What was the budget of The Matrix?")
    assert len(result.results) > 0
