import pytest
import requests
from pipeline import KGPipeline

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_capital_most_populous_country():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What is the capital of the most populous country in the world?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_einstein_wife_birthplace():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In which city was Albert Einstein's wife born?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_italy():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What is the highest mountain in Italy?")
    assert len(results) > 0
    assert any("Mont Blanc" in str(row) or "Monte Bianco" in str(row) or "Blanc" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mayor_capital_france():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Who is the mayor of the capital of France?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_director_inception_birth_country():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In what country was the director of Inception born?")
    assert len(results) > 0
    assert any("United Kingdom" in str(row) or "UK" in str(row) or "England" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_real_madrid_stadium_city():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In which city is the Real Madrid stadium located?")
    assert len(results) > 0
    assert any("Madrid" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_shakespeare_hometown_country():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In which country is William Shakespeare's hometown located?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_penicillin_discoverer_birthdate():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What is the birth date of the person who discovered penicillin?")
    assert len(results) > 0
    assert any("1881" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_polonium_discoverer():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Who discovered polonium?")
    assert len(results) > 0
    assert any("Curie" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mona_lisa_museum():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In which museum is the Mona Lisa located?")
    assert len(results) > 0
    assert any("Louvre" in str(row) for row in results)
