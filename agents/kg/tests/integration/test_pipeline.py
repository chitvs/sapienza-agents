import pytest
import requests
from pipeline import KGPipeline

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_albert_einstein_birth_date():
    pipeline = KGPipeline()
    result = pipeline.run("What is the birth date of Albert Einstein?")
    assert len(result.results) > 0
    assert "1879-03-14" in str(result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_real_madrid_president():
    pipeline = KGPipeline()
    result = pipeline.run("Who is the president of Real Madrid?")
    assert len(result.results) > 0
    res_str = str(result.results)
    assert "Florentino Pérez" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_france_capital():
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of France?")
    assert len(result.results) > 0
    res_str = str(result.results)
    assert "Paris" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_descriptive_query():
    pipeline = KGPipeline()
    result = pipeline.run("Who is Minerva?")
    assert len(result.results) > 0
    res_str = str(result.results).lower()
    assert any(word in res_str for word in ["war", "wisdom", "goddess", "roman", "strategic"])

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_sapienza_founding_date():
    pipeline = KGPipeline()
    result = pipeline.run("When was Sapienza University founded?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_elevation_rome():
    pipeline = KGPipeline()
    result = pipeline.run("What is the elevation of Rome?")
    assert len(result.results) > 0
    assert any("21" in str(row) for row in result.results)
