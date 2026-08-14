"""
Test della metrica di valutazione QALD.

Sono i numeri che finiscono nella tesi: un difetto qui non si vede da nessuna parte, perché
produce un punteggio plausibile invece di un errore.
"""
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "benchmarks" / "evaluate_qald.py"
_spec = importlib.util.spec_from_file_location("evaluate_qald", _MODULE_PATH)
evaluate_qald = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate_qald)

DBPEDIA = evaluate_qald.DBPEDIA_PREDICATES

@pytest.mark.parametrize(
    "value, expected",
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
def test_normalize_survives_pseudo_numbers(value, expected):
    assert evaluate_qald.normalize(value) == expected

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
    precision, recall, f1 = evaluate_qald.score_items([{"a"}, {"b"}], [{"a"}])
    assert (precision, recall) == (1.0, 0.5)
    assert f1 == pytest.approx(2 / 3)

def test_wrong_answer_scores_zero():
    assert evaluate_qald.score_items([{"a"}], [{"z"}]) == (0.0, 0.0, 0.0)

def test_alias_sets_are_deterministic():
    """alias_sets iterava un set, il cui ordine cambia fra processi con l'hash randomizzato."""
    values = {"http://www.wikidata.org/entity/Q937", "albert einstein", "zzz"}
    assert evaluate_qald.alias_sets(values) == evaluate_qald.alias_sets(set(values))

def test_a_dbpedia_uri_is_an_alias_of_its_label():
    """Su DBpedia il nome locale è già l'etichetta, quindi il gold si confronta senza rete."""
    forms = evaluate_qald.alias_sets({"http://dbpedia.org/resource/Mountain_Time_Zone"})
    assert "mountain time zone" in forms[0]

def test_metadata_are_not_answers():
    """_provenance e _sources sono metadati: contarli come risposte falserebbe la precisione."""
    row = {
        "x": "Albert Einstein",
        "_sources": {"x": "http://www.wikidata.org/entity/Q937"},
        "_provenance": {"source_kg": "wikidata", "timestamp": "2026-08-11T00:00:00+00:00"},
    }
    assert evaluate_qald.system_answers([row]) == {"http://www.wikidata.org/entity/q937"}

def test_ask_answers_are_booleans():
    assert evaluate_qald.system_answers([{"boolean": True}]) is True
    assert evaluate_qald.system_answers([{"boolean": "false"}]) is False

def test_a_false_ask_gold_is_a_valid_answer():
    """Confondere "falso" con "nessuna risposta" sposterebbe in blocco l'F1 delle ASK."""
    assert evaluate_qald.score(False, False) == (1.0, 1.0, 1.0)
    assert evaluate_qald.score(True, False) == (0.0, 0.0, 0.0)

def test_empty_gold_and_empty_answer_follow_the_qald_convention():
    assert evaluate_qald.score(set(), set()) == (1.0, 1.0, 1.0)
    assert evaluate_qald.score({"a"}, set()) == (0.0, 0.0, 0.0)

def test_only_a_non_empty_gold_is_usable():
    """Un gold vuoto darebbe F1=1.0 a una pipeline esplosa; un ASK falso resta valutabile."""
    assert evaluate_qald.has_usable_gold({"a"})
    assert evaluate_qald.has_usable_gold(False)
    assert not evaluate_qald.has_usable_gold(set())
    assert not evaluate_qald.has_usable_gold(None)

def test_qualifiers_count_as_hops():
    """Contando solo wdt:/p:, una query con ps:/pq: risultava "single" proprio perché più difficile."""
    query = (
        "SELECT ?x WHERE { wd:Q1 p:P39 ?s . ?s ps:P39 ?x . ?s pq:P580 ?d }"
    )
    assert evaluate_qald.question_kind(query) == "multi"

def test_a_single_triple_stays_a_direct_question():
    assert evaluate_qald.question_kind("SELECT ?x WHERE { wd:Q937 wdt:P569 ?x }") == "single"

def test_ask_and_count_are_recognised():
    assert evaluate_qald.question_kind("ASK { wd:Q1 wdt:P31 wd:Q5 }") == "ask"
    assert evaluate_qald.question_kind("SELECT (COUNT(?x) AS ?n) WHERE { ?x wdt:P31 wd:Q5 }") == "count"

def test_a_dbpedia_class_filter_is_not_an_extra_hop():
    """Su DBpedia le classi si distinguono dalle proprietà per la maiuscola del nome locale."""
    query = "SELECT ?uri WHERE { ?uri rdf:type onto:Mountain }"
    assert evaluate_qald.question_kind(query, DBPEDIA) == "single"

def test_dbpedia_hops_are_counted_across_notations():
    """Prefissi, URI completi e la `a` di rdf:type sono la stessa cosa: tre hop."""
    query = (
        "SELECT ?uri WHERE { ?uri a onto:Mountain ; onto:elevation ?e ; "
        "<http://dbpedia.org/ontology/locatedInArea> <http://dbpedia.org/resource/Germany> }"
    )
    assert evaluate_qald.question_kind(query, DBPEDIA) == "multi"

def test_the_two_benchmarks_target_different_graphs():
    assert evaluate_qald.BENCHMARKS["qald10"].target_kg == "wikidata"
    assert evaluate_qald.BENCHMARKS["qald9plus"].target_kg == "dbpedia"
