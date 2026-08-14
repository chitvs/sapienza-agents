"""
Test di integrazione end-to-end su DBpedia.

Richiedono Ollama attivo, l'endpoint pubblico DBpedia raggiungibile e l'indice FAISS
dell'ontologia già costruito (scripts/ingest_dbpedia.py). Se manca qualcosa i test
vengono saltati invece di fallire.
"""
from pathlib import Path

import pytest
import requests

from pipeline import KGPipeline
from conftest import contains_answer
from conftest import is_ollama_running

_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "dbpedia_ontology"

def is_dbpedia_reachable() -> bool:
    try:
        return requests.get("https://dbpedia.org/sparql", timeout=5).status_code < 500
    except Exception:
        return False

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_dbpedia_reachable() and (_INDEX_DIR / "properties.faiss").exists()),
    reason="richiede Ollama, l'endpoint DBpedia e l'indice ontologico (scripts/ingest_dbpedia.py)",
)

@pytest.fixture(scope="module")
def pipeline():
    return KGPipeline(target_kg="dbpedia")

@requires_stack
def test_birth_place(pipeline):
    """proprietà diretta su una risorsa."""
    result = pipeline.run("Where was Albert Einstein born?")
    assert len(result.results) > 0
    assert contains_answer(result, "Ulm")

@requires_stack
def test_director_with_explicit_label(pipeline):
    """richiede rdfs:label esplicito: su DBpedia non esiste un servizio di etichette."""
    result = pipeline.run("Who directed The Matrix?")
    assert len(result.results) > 0
    assert contains_answer(result, "Wachowski")

@requires_stack
def test_capital(pipeline):
    result = pipeline.run("What is the capital of France?")
    assert len(result.results) > 0
    assert contains_answer(result, "Paris")

@requires_stack
def test_count_aggregation(pipeline):
    result = pipeline.run("How many films did Christopher Nolan direct?")
    assert len(result.results) > 0

@requires_stack
def test_multi_hop_to_final_value(pipeline):
    """catena a due hop: il risultato deve essere la popolazione, non il nome della capitale."""
    result = pipeline.run("What is the population of the capital of Japan?")
    assert len(result.results) > 0
    assert any(any(ch.isdigit() for ch in str(v)) for row in result.results for v in row.values())
