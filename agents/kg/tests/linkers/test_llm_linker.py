import pytest
import requests
from connectors.base_connector import EntityCandidate
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import LinkedEntity
from linkers.llm_linker import LLMLinker

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_extract_proper_nouns_standalone():
    """Test the regex-based fallback extraction of proper nouns."""
    linker = LLMLinker.__new__(LLMLinker)
    nouns_en = linker._fallback_extract_proper_nouns("What is the capital of France?")
    assert "France" in nouns_en

    nouns_it = linker._fallback_extract_proper_nouns("Chi è il presidente della SS Lazio?")
    assert "SS Lazio" in nouns_it

    nouns_person = linker._fallback_extract_proper_nouns("Chi è Sergio Mattarella?")
    assert "Sergio Mattarella" in nouns_person

def test_disambiguate_candidates_json_parsing():
    linker = LLMLinker.__new__(LLMLinker)
    class MockLLM:
        def chat(self, system_prompt, user_content, temperature):
            # Simuliamo che l'LLM menzioni Q15817918 nel testo ma scelga Q126916 nel JSON
            return 'Thinking: Q15817918 is a journal, but Q126916 is a goddess.\n```json\n{"selected_id": "Q126916"}\n```'
        def load_prompt(self, filename, **kwargs):
            return "prompt"
        def clean_code_block(self, text):
            return '{"selected_id": "Q126916"}'

    linker.llm_client = MockLLM()
    linker.connector = WikimediaConnector()
    cands = [
        EntityCandidate(id="Q126916", label="Minerva", description="Roman goddess"),
        EntityCandidate(id="Q15817918", label="Minerva", description="journal"),
    ]
    res = linker._disambiguate_candidates("Chi è Minerva?", "Minerva", cands)
    assert res.id == "Q126916"

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_disambiguate_candidates_context():
    connector = WikimediaConnector()
    linker = LLMLinker(connector=connector)
    cands = [
        EntityCandidate(id="Q126916", label="Minerva", description="Roman goddess of wisdom"),
        EntityCandidate(id="Q15817918", label="Minerva", description="academic journal published by Springer"),
    ]
    cand_goddess = linker._disambiguate_candidates("Chi è Minerva?", "Minerva", cands)
    assert cand_goddess.id == "Q126916"

    cand_journal = linker._disambiguate_candidates("Qual è l editore del journal Minerva?", "Minerva", cands)
    assert cand_journal.id == "Q15817918"

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_link():
    connector = WikimediaConnector()
    linker = LLMLinker(connector=connector)
    entities = linker.link("Qual è la data di nascita di Albert Einstein?")
    assert len(entities) > 0
    assert any(e.id == "Q937" or "Einstein" in e.mention for e in entities)
