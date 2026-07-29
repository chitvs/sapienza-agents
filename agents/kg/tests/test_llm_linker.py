import pytest
import requests
from connectors.wikimedia_connector import WikimediaConnector
from linkers.llm_linker import LLMLinker

def is_ollama_running():
    try:
        res = requests.get("http://localhost:11434/", timeout=1.0)
        return res.status_code == 200
    except requests.exceptions.RequestException:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_llm_linker_einstein():
    connector = WikimediaConnector()
    linker = LLMLinker(connector=connector, model_name="llama3.2")

    question = "Qual è la data di nascita di Albert Einstein?"
    entities = linker.link(question)

    assert len(entities) > 0
    assert entities[0].qid == "Q937"
    assert "Einstein" in entities[0].label
