"""
Copertura estesa della pipeline Wikidata.
"""

import pytest
from pipeline import KGPipeline
from conftest import contains_answer
from conftest import is_ollama_running

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_switzerland_official_languages_list():
    pipeline = KGPipeline()
    result = pipeline.run("What are the official languages of Switzerland?")
    assert len(result.results) > 0
    assert contains_answer(result, "German")

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_switzerland_official_languages_count():
    pipeline = KGPipeline()
    result = pipeline.run("How many official languages does Switzerland have?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_titanic_director_citizenship_capital():
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of the country of citizenship of the director of Titanic?")
    assert len(result.results) > 0
    assert any(contains_answer(result, c) for c in ("Ottawa", "Wellington"))

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_us_president_2010():
    pipeline = KGPipeline()
    result = pipeline.run("Who was the president of the United States in 2010?")
    assert len(result.results) > 0
    assert contains_answer(result, "Obama")

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_bach_children_count():
    pipeline = KGPipeline()
    result = pipeline.run("How many children did Johann Sebastian Bach have?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_eiffel_tower_country():
    pipeline = KGPipeline()
    result = pipeline.run("What is the highest mountain in the country where the Eiffel Tower is located?")
    assert len(result.results) > 0
    assert any(contains_answer(result, n) for n in ("Mont Blanc", "Blanc"))

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_official_language_capital_paris():
    pipeline = KGPipeline()
    result = pipeline.run("What is the official language of the country whose capital is Paris?")
    assert len(result.results) > 0
    assert contains_answer(result, "French")

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mars_moons_count():
    pipeline = KGPipeline()
    result = pipeline.run("How many moons does Mars have?")
    assert len(result.results) > 0
