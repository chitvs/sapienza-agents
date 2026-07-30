import pytest
import requests
from translators.sparql_translator import SPARQLTranslator

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_translate():
    translator = SPARQLTranslator(model_name="llama3.2")
    query = translator.translate(
        question="Qual è la data di nascita di Albert Einstein?",
        schema_context="Albert Einstein (wd:Q937), data di nascita (wdt:P569)",
    )
    assert "SELECT" in query.upper()
    assert "wd:Q937" in query
