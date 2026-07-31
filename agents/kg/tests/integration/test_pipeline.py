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
    results, query = pipeline.run("Qual è la data di nascita di Albert Einstein?")
    assert len(results) > 0
    assert "1879-03-14" in str(results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_real_madrid_president():
    pipeline = KGPipeline()
    results, query = pipeline.run("Chi è il presidente del Real Madrid?")
    assert len(results) > 0
    res_str = str(results)
    assert "Florentino Pérez" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_france_capital():
    pipeline = KGPipeline()
    results, query = pipeline.run("What is the capital of France?")
    assert len(results) > 0
    res_str = str(results)
    assert "Paris" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_descriptive_query():
    pipeline = KGPipeline()
    results, query = pipeline.run("Chi è Minerva?")
    assert len(results) > 0
    res_str = str(results).lower()
    assert "divinità romana della guerra e della saggezza" in res_str