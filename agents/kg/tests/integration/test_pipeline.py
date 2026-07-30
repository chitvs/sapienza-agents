import pytest
import requests
from pipeline import KGPipeline

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_run():
    pipeline = KGPipeline()
    results, query = pipeline.run("Qual è la data di nascita di Albert Einstein?")
    assert len(results) > 0
    assert "1879-03-14" in str(results[0])
