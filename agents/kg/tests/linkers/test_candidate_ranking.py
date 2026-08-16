"""
Test del ranking dei candidati quando l'LLM non è conclusivo.
"""

import pytest
from connectors.base_connector import EntityCandidate
from linkers.entity_linker import EntityLinker

class _FakeConnector:
    def __init__(self, prominence: dict[str, float] | None = None):
        self.prominence = prominence or {}

    def candidate_prominence(self, candidates):
        return dict(self.prominence)

    def is_valid_candidate(self, candidate):
        return bool(candidate.id)

@pytest.fixture
def linker():
    return EntityLinker.__new__(EntityLinker)

def test_rescale_with_equal_values_does_not_divide_by_zero(linker):
    assert EntityLinker._rescale([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]

def test_rescale_maps_the_extremes_to_zero_and_one(linker):
    assert EntityLinker._rescale([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]

def test_prominence_overturns_the_search_order(linker, monkeypatch):
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.5] * len(c))
    linker.connector = _FakeConnector({"Q1": 3.0, "Q2": 500.0, "Q3": 1.0})
    candidates = [EntityCandidate(id=q, label="x") for q in ("Q1", "Q2", "Q3")]
    assert linker._rank_candidates("a question", candidates).id == "Q2"

def test_with_only_two_candidates_the_signals_cancel_out(linker, monkeypatch):
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.5] * len(c))
    linker.connector = _FakeConnector({"Q1": 3.0, "Q2": 500.0})
    candidates = [EntityCandidate(id="Q1", label="x"), EntityCandidate(id="Q2", label="x")]
    assert linker._rank_candidates("a question", candidates).id == "Q1"

def test_a_kg_without_prominence_does_not_alter_the_ranking(linker, monkeypatch):
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.0, 1.0, 0.2])
    linker.connector = _FakeConnector()
    candidates = [EntityCandidate(id=q, label="x") for q in ("Q1", "Q2", "Q3")]
    assert linker._rank_candidates("a question", candidates).id == "Q2"

def test_a_single_candidate_needs_no_computation(linker):
    only_one = [EntityCandidate(id="Q1", label="x")]
    assert linker._rank_candidates("a question", only_one).id == "Q1"

class _FakeLLM:
    def __init__(self, parsed):
        self.parsed = parsed

    def clean_code_block(self, raw_output):
        return self.parsed

def test_an_id_contained_in_another_stays_an_unambiguous_choice(linker):
    linker.llm_client = _FakeLLM("not json")
    by_id = {"Berlin": "A", "Berlin,_Ohio": "B"}
    assert linker._select_from_output("I choose Berlin,_Ohio", by_id) == "B"

def test_two_quoted_ids_are_not_a_choice(linker):
    linker.llm_client = _FakeLLM("not json")
    by_id = {"Berlin": "A", "Munich": "C"}
    assert linker._select_from_output("Berlin or Munich", by_id) is None

def test_the_json_wins_over_a_merely_mentioned_id(linker):
    linker.llm_client = _FakeLLM('{"selected_id": "Q2"}')
    raw = 'Q1 looks plausible but I choose the other one.\n{"selected_id": "Q2"}'
    assert linker._select_from_output(raw, {"Q1": "A", "Q2": "B"}) == "B"
