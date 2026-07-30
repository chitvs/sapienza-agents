import pytest
import requests
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import LinkedEntity
from linkers.llm_linker import LLMLinker

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_link():
    connector = WikimediaConnector()
    linker = LLMLinker(connector=connector, model_name="llama3.2")
    entities = linker.link("Qual è la data di nascita di Albert Einstein?")
    assert len(entities) > 0
    assert any(e.qid == "Q937" or "Einstein" in e.mention for e in entities)
