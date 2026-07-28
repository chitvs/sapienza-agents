# Test per verificare se Text2SPARQL funziona, è necessario ollama in locale
# todo: implementare docker e collegarsi direttamente lì

import pytest
import requests
from translators.sparql_translator import SPARQLTranslator

# helper per verificare se Ollama è attivo in locale
def is_ollama_running():
    try:
        res = requests.get("http://localhost:11434/", timeout=1.0)
        return res.status_code == 200
    except requests.exceptions.RequestException:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo su http://localhost:11434")
def test_sparql_translator():
    translator = SPARQLTranslator(model_name="llama3.2")
    
    question = "Qual è la data di nascita di Albert Einstein?"
    context = "Albert Einstein (wd:Q937), data di nascita (wdt:P569)"
    
    query = translator.translate(question=question, schema_context=context)

    assert "SELECT" in query.upper()
    assert "wd:Q937" in query
