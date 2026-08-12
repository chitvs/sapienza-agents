"""
Test del ripiego che sceglie il candidato quando l'LLM non è conclusivo.

È il percorso che decide l'entità nella maggior parte dei casi reali, ed è logica pura:
non serve né LLM né rete, basta un connettore finto che dichiari la notorietà.
"""
import pytest

from connectors.base_connector import EntityCandidate
from linkers.entity_linker import EntityLinker

class ConnettoreFinto:
    def __init__(self, notorieta: dict[str, float] | None = None):
        self.notorieta = notorieta or {}

    def candidate_prominence(self, candidates):
        return dict(self.notorieta)

    def is_valid_candidate(self, candidate):
        return bool(candidate.id)

@pytest.fixture
def linker():
    return EntityLinker.__new__(EntityLinker)

def test_rescale_con_valori_uguali_non_divide_per_zero(linker):
    """Tutti i candidati a pari merito devono ricevere 0.5, non un errore."""
    assert EntityLinker._rescale([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]

def test_rescale_porta_gli_estremi_a_zero_e_uno(linker):
    assert EntityLinker._rescale([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]

def test_notorieta_ribalta_l_ordine_di_ricerca(linker, monkeypatch):
    """Con contesto neutro deve vincere il candidato più noto, anche se non è il primo."""
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.5] * len(c))
    linker.connector = ConnettoreFinto({"Q1": 3.0, "Q2": 500.0, "Q3": 1.0})
    candidati = [EntityCandidate(id=q, label="x") for q in ("Q1", "Q2", "Q3")]
    assert linker._rank_candidates("domanda", candidati).id == "Q2"

def test_con_due_soli_candidati_i_segnali_si_annullano(linker, monkeypatch):
    """Proprietà nota del ranking: riportando i punteggi agli estremi 0 e 1, con due
    candidati notorietà e rango sono esattamente opposti e la scelta torna al primo
    della ricerca. Serve un terzo candidato, o un contesto discriminante, per decidere."""
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.5] * len(c))
    linker.connector = ConnettoreFinto({"Q1": 3.0, "Q2": 500.0})
    candidati = [EntityCandidate(id="Q1", label="x"), EntityCandidate(id="Q2", label="x")]
    assert linker._rank_candidates("domanda", candidati).id == "Q1"

def test_un_kg_senza_notorieta_non_altera_la_classifica(linker, monkeypatch):
    """candidate_prominence vuoto deve degradare a un segnale neutro, non azzerare tutto."""
    monkeypatch.setattr(EntityLinker, "_context_scores", lambda self, q, c: [0.0, 1.0, 0.2])
    linker.connector = ConnettoreFinto()
    candidati = [EntityCandidate(id=q, label="x") for q in ("Q1", "Q2", "Q3")]
    # senza notorietà decidono contesto e rango, e il contesto può ancora vincere: l'unico
    # che non può è l'ultimo della lista, che parte da rango zero
    assert linker._rank_candidates("domanda", candidati).id == "Q2"

def test_un_solo_candidato_non_richiede_calcoli(linker):
    solo = [EntityCandidate(id="Q1", label="x")]
    assert linker._rank_candidates("domanda", solo).id == "Q1"

class LLMFinto:
    def __init__(self, parsed):
        self.parsed = parsed

    def clean_code_block(self, raw_output):
        return self.parsed

def test_id_contenuto_in_un_altro_resta_una_scelta_univoca(linker):
    """Su DBpedia un id può contenerne un altro: Berlin dentro Berlin,_Ohio."""
    linker.llm_client = LLMFinto("non è json")
    mappa = {"Berlin": "A", "Berlin,_Ohio": "B"}
    assert linker._select_from_output("scelgo Berlin,_Ohio", mappa) == "B"

def test_due_id_citati_non_sono_una_scelta(linker):
    """Se il modello ne nomina due la decisione non è deducibile: si ripiega sul ranking."""
    linker.llm_client = LLMFinto("non è json")
    mappa = {"Berlin": "A", "Munich": "C"}
    assert linker._select_from_output("Berlin oppure Munich", mappa) is None

def test_il_json_vince_sull_id_solo_nominato(linker):
    """L'id scelto nel JSON deve prevalere su quello citato nel ragionamento."""
    linker.llm_client = LLMFinto('{"selected_id": "Q2"}')
    grezzo = 'Q1 sembra plausibile ma scelgo l\'altro.\n{"selected_id": "Q2"}'
    assert linker._select_from_output(grezzo, {"Q1": "A", "Q2": "B"}) == "B"
