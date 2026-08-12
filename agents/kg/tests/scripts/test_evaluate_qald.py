"""
Test della metrica di valutazione QALD.

Sono i numeri che finiscono nella tesi: un difetto qui non si vede da nessuna parte, perché
produce un punteggio plausibile invece di un errore.
"""
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_qald.py"
_spec = importlib.util.spec_from_file_location("evaluate_qald", _MODULE_PATH)
evaluate_qald = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate_qald)

@pytest.mark.parametrize(
    "valore, atteso",
    [
        ("4.0", "4"),
        ("+1879-03-14T00:00:00Z", "1879-03-14"),
        ("The Matrix", "the matrix"),
        # int(float("Infinity")) solleva OverflowError, che non è un ValueError: senza
        # intercettarlo una valutazione di ore moriva senza scrivere il report
        ("Infinity", "infinity"),
        ("-Infinity", "-infinity"),
        ("NaN", "nan"),
    ],
)
def test_normalize_survives_pseudo_numbers(valore, atteso):
    assert evaluate_qald.normalize(valore) == atteso

def test_matching_is_maximum_not_greedy():
    """Con etichette condivise l'accoppiamento avido dimezzava l'F1 di una risposta esatta."""
    gold = [{"a", "b"}, {"b"}]
    ours = [{"b"}, {"a"}]
    assert evaluate_qald.score_items(gold, ours) == (1.0, 1.0, 1.0)

def test_matching_does_not_depend_on_order():
    gold = [{"a", "b"}, {"b"}]
    assert evaluate_qald.score_items(gold, [{"a"}, {"b"}]) == evaluate_qald.score_items(
        list(reversed(gold)), [{"b"}, {"a"}]
    )

def test_partial_answer_is_scored_partially():
    precisione, richiamo, f1 = evaluate_qald.score_items([{"a"}, {"b"}], [{"a"}])
    assert (precisione, richiamo) == (1.0, 0.5)
    assert f1 == pytest.approx(2 / 3)

def test_wrong_answer_scores_zero():
    assert evaluate_qald.score_items([{"a"}], [{"z"}]) == (0.0, 0.0, 0.0)

def test_alias_sets_are_deterministic():
    """alias_sets iterava un set, il cui ordine cambia fra processi con l'hash randomizzato."""
    valori = {"http://www.wikidata.org/entity/Q937", "albert einstein", "zzz"}
    assert evaluate_qald.alias_sets(valori) == evaluate_qald.alias_sets(set(valori))

def test_i_metadati_non_diventano_risposte():
    """_provenance e _sources sono metadati: contarli come risposte falserebbe la precisione."""
    riga = {
        "x": "Albert Einstein",
        "_sources": {"x": "http://www.wikidata.org/entity/Q937"},
        "_provenance": {"source_kg": "wikidata", "timestamp": "2026-08-11T00:00:00+00:00"},
    }
    assert evaluate_qald.system_answers([riga]) == {"http://www.wikidata.org/entity/q937"}

def test_le_ask_restituiscono_un_booleano():
    assert evaluate_qald.system_answers([{"boolean": True}]) is True
    assert evaluate_qald.system_answers([{"boolean": "false"}]) is False

def test_un_gold_ask_falso_e_una_risposta_valida():
    """Confondere "falso" con "nessuna risposta" sposterebbe in blocco l'F1 delle ASK."""
    assert evaluate_qald.score(False, False) == (1.0, 1.0, 1.0)
    assert evaluate_qald.score(True, False) == (0.0, 0.0, 0.0)

def test_gold_vuoto_e_risposta_vuota_seguono_la_convenzione_qald():
    assert evaluate_qald.score(set(), set()) == (1.0, 1.0, 1.0)
    assert evaluate_qald.score({"a"}, set()) == (0.0, 0.0, 0.0)

def test_i_qualificatori_contano_come_hop():
    """Contando solo wdt:/p:, una query con ps:/pq: risultava "single" proprio perché più difficile."""
    query = (
        "SELECT ?x WHERE { wd:Q1 p:P39 ?s . ?s ps:P39 ?x . ?s pq:P580 ?d }"
    )
    assert evaluate_qald.question_kind(query) == "multi"

def test_una_sola_tripla_resta_una_domanda_diretta():
    assert evaluate_qald.question_kind("SELECT ?x WHERE { wd:Q937 wdt:P569 ?x }") == "single"

def test_le_ask_e_i_conteggi_sono_riconosciuti():
    assert evaluate_qald.question_kind("ASK { wd:Q1 wdt:P31 wd:Q5 }") == "ask"
    assert evaluate_qald.question_kind("SELECT (COUNT(?x) AS ?n) WHERE { ?x wdt:P31 wd:Q5 }") == "count"
