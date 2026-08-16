"""
Test dell'entity linker.
"""

import pytest
from connectors.base_connector import EntityCandidate
from connectors.wikidata_connector import WikidataConnector
from linkers.entity_linker import EntityLinker
from conftest import is_ollama_running

@pytest.mark.parametrize(
    "mention, expected",
    [
        ("Shakespeare's", "Shakespeare"),
        ("Shakespeare’s", "Shakespeare"),
        ("the Beatles'", "the Beatles"),
        ("Tom Hanks", "Tom Hanks"),
        ("United States", "United States"),
        ("The Rolling Stones", "The Rolling Stones"),
        ("Blue Cross", "Blue Cross"),
        ("Paris", "Paris"),
    ],
)
def test_normalize_mention_preserves_proper_nouns(mention, expected):
    assert EntityLinker._normalize_mention(mention) == expected

def test_extract_proper_nouns_standalone():
    linker = EntityLinker.__new__(EntityLinker)
    nouns_en = linker._fallback_extract_proper_nouns("What is the capital of France?")
    assert "France" in nouns_en

    nouns_it = linker._fallback_extract_proper_nouns("Chi è il presidente della SS Lazio?")
    assert "SS Lazio" in nouns_it

    nouns_person = linker._fallback_extract_proper_nouns("Chi è Sergio Mattarella?")
    assert "Sergio Mattarella" in nouns_person

class _FakeLLM:
    def __init__(self, raw_output: str, parsed: str) -> None:
        self.raw_output = raw_output
        self.parsed = parsed

    def chat(self, system_prompt, user_content, temperature=0.0, top_p=None):
        return self.raw_output

    def load_prompt(self, prompt_filename, **kwargs):
        return "prompt"

    def clean_code_block(self, raw_output):
        return self.parsed

def test_disambiguate_candidates_reads_the_json_choice():
    linker = EntityLinker.__new__(EntityLinker)
    linker.llm_client = _FakeLLM(
        raw_output='Thinking: Q126916 is a goddess, but the question is about the journal.\n'
        '```json\n{"selected_id": "Q15817918"}\n```',
        parsed='{"selected_id": "Q15817918"}',
    )
    linker.connector = WikidataConnector()
    cands = [
        EntityCandidate(id="Q126916", label="Minerva", description="Roman goddess"),
        EntityCandidate(id="Q15817918", label="Minerva", description="journal"),
    ]
    res = linker._disambiguate_candidates("Who publishes the journal Minerva?", "Minerva", cands)
    assert res.id == "Q15817918"

def test_possessive_is_stripped_only_if_the_kg_knows_nothing():
    class _FakeConnector:
        def __init__(self, known):
            self.known = known
            self.queried = []

        def search_entity(self, text, limit=5):
            self.queried.append(text)
            return [EntityCandidate(id="X1", label=text, description="")] if text in self.known else []

    linker = EntityLinker.__new__(EntityLinker)

    linker.connector = _FakeConnector({"McDonald's"})
    mention, candidates = linker._search_mention("McDonald's")
    assert mention == "McDonald's" and candidates

    linker.connector = _FakeConnector({"Shakespeare"})
    mention, candidates = linker._search_mention("Shakespeare's")
    assert mention == "Shakespeare" and candidates

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_disambiguate_candidates_context():
    connector = WikidataConnector()
    linker = EntityLinker(connector=connector)
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
    connector = WikidataConnector()
    linker = EntityLinker(connector=connector)
    entities = linker.link("Qual è la data di nascita di Albert Einstein?")
    assert len(entities) > 0
    assert any(e.id == "Q937" or "Einstein" in e.mention for e in entities)
