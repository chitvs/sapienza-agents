import pytest
import requests
from pipeline import KGPipeline

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_capital_germany():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What is the capital of Germany?")
    assert len(results) > 0
    assert any("Berlin" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_penicillin_discoverer():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Who discovered penicillin?")
    assert len(results) > 0
    assert any("Fleming" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_julius_caesar_birthplace():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Where was Julius Caesar born?")
    assert len(results) > 0
    assert any("Rome" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_psg_coach():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Who is the coach of Paris Saint-Germain?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_spain():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What is the highest mountain in Spain?")
    assert len(results) > 0
    assert any("Teide" in str(row) or "Mulhacén" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_world_war_two_end():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("When did World War II end?")
    assert len(results) > 0
    assert any("1945" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_marie_curie_birth():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("When was Marie Curie born?")
    assert len(results) > 0
    assert any("1867" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_juventus_stadium():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("In which stadium does Juventus play?")
    assert len(results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_tokyo_country():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("What country is Tokyo located in?")
    assert len(results) > 0
    assert any("Japan" in str(row) for row in results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_divine_comedy_author():
    pipeline = KGPipeline()
    results, query, _ = pipeline.run("Who wrote the Divine Comedy?")
    assert len(results) > 0
    assert any("Dante" in str(row) for row in results)
