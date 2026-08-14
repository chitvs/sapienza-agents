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
Answer = evaluate_qald.Answer

def literal(*forms: str) -> "evaluate_qald.Answer":
    """Risposta senza URI: un letterale si accoppia per sola intersezione delle forme."""
    return Answer(None, frozenset(forms))

def entity(uri: str, *labels: str) -> "evaluate_qald.Answer":
    """Risposta identificata da un URI, con le etichette che la rappresentano."""
    return Answer(uri, frozenset({uri, *labels}))

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
    gold = [literal("a", "b"), literal("b")]
    ours = [literal("b"), literal("a")]
    assert evaluate_qald.score_items(gold, ours) == (1.0, 1.0, 1.0)

def test_matching_survives_thousands_of_answers():
    """La versione ricorsiva moriva di RecursionError, e QALD-9-plus ha una domanda da 1712."""
    gold = [entity(f"http://www.wikidata.org/entity/q{i}", "mercury") for i in range(1500)]
    assert evaluate_qald.score_items(gold, list(gold)) == (1.0, 1.0, 1.0)

def test_an_ambiguous_label_does_not_bridge_two_entities():
    """"Mercury" è un pianeta e un elemento: accettare l'etichetta darebbe F1=1.0 proprio
    all'errore di disambiguazione che il benchmark deve misurare."""
    gold = [entity("http://www.wikidata.org/entity/q308", "mercury")]
    ours = [entity("http://www.wikidata.org/entity/q925", "mercury")]
    assert evaluate_qald.score_items(gold, ours) == (0.0, 0.0, 0.0)

def test_a_label_still_bridges_an_entity_and_a_literal():
    """La query gold proietta l'entità e la nostra ?xLabel: senza il ponte sarebbe un errore."""
    gold = [entity("http://www.wikidata.org/entity/q937", "albert einstein")]
    ours = [literal("albert einstein")]
    assert evaluate_qald.score_items(gold, ours) == (1.0, 1.0, 1.0)

def test_matching_does_not_depend_on_order():
    gold = [literal("a", "b"), literal("b")]
    assert evaluate_qald.score_items(gold, [literal("a"), literal("b")]) == evaluate_qald.score_items(
        list(reversed(gold)), [literal("b"), literal("a")]
    )

def test_partial_answer_is_scored_partially():
    precision, recall, f1 = evaluate_qald.score_items([literal("a"), literal("b")], [literal("a")])
    assert (precision, recall) == (1.0, 0.5)
    assert f1 == pytest.approx(2 / 3)

def test_wrong_answer_scores_zero():
    assert evaluate_qald.score_items([literal("a")], [literal("z")]) == (0.0, 0.0, 0.0)

def test_alias_sets_are_ordered():
    """L'ordine di iterazione di un set cambia fra processi: senza sorted() il report non
    sarebbe riproducibile. Asserire l'uguaglianza fra due chiamate non lo verificherebbe."""
    values = {"http://www.wikidata.org/entity/Q937", "albert einstein", "zzz"}
    produced = [next(iter(a.forms & values)) for a in evaluate_qald.alias_sets(values)]
    assert produced == sorted(values)

def test_a_dbpedia_uri_is_an_alias_of_its_label():
    """Su DBpedia il nome locale è già l'etichetta, quindi il gold si confronta senza rete."""
    answers = evaluate_qald.alias_sets({"http://dbpedia.org/resource/Mountain_Time_Zone"})
    assert "mountain time zone" in answers[0].forms

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

def test_an_aggregate_outside_the_projection_is_not_a_count_question():
    """Con HAVING(COUNT(...)) la risposta attesa è un elenco di entità, non un numero."""
    query = (
        "SELECT ?uri WHERE { ?uri dbo:country ?c . ?c dbo:cave ?cave } "
        "GROUP BY ?uri HAVING (COUNT(?cave) > 2)"
    )
    assert evaluate_qald.question_kind(query, DBPEDIA) == "multi"

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

def _fake_entries(counts: dict[str, int]) -> list[dict]:
    """Domande finte di un tipo noto, per verificare le quote del campionamento."""
    shapes = {
        "ask": "ASK { wd:Q1 wdt:P31 wd:Q5 }",
        "count": "SELECT (COUNT(?x) AS ?n) WHERE { ?x wdt:P31 wd:Q5 }",
        "single": "SELECT ?x WHERE { wd:Q1 wdt:P569 ?x }",
        "multi": "SELECT ?x WHERE { wd:Q1 wdt:P26 ?s . ?s wdt:P19 ?x }",
    }
    return [
        {"id": f"{kind}{i}", "query": {"sparql": shapes[kind]}}
        for kind, n in counts.items() for i in range(n)
    ]

def test_the_sample_has_exactly_the_requested_size():
    """Arrotondando ogni quota per conto suo si otteneva un campione di 99 su 100 richieste."""
    entries = _fake_entries({"ask": 61, "count": 89, "multi": 113, "single": 131})
    for size in (10, 30, 100, 250):
        assert len(evaluate_qald.stratified_sample(entries, size, 0, evaluate_qald.WIKIDATA_PREDICATES)) == size

def test_the_sample_keeps_the_proportions_of_the_dataset():
    """Un max(1, ...) dava alle classi rare un peso che nel dataset non hanno."""
    entries = _fake_entries({"ask": 4, "multi": 96})
    sample = evaluate_qald.stratified_sample(entries, 25, 0, evaluate_qald.WIKIDATA_PREDICATES)
    kinds = [e["id"].rstrip("0123456789") for e in sample]
    assert kinds.count("ask") == 1

def test_the_sample_is_reproducible_with_the_same_seed():
    entries = _fake_entries({"ask": 20, "single": 80})
    ids = lambda seed: [e["id"] for e in evaluate_qald.stratified_sample(
        entries, 15, seed, evaluate_qald.WIKIDATA_PREDICATES)]
    assert ids(7) == ids(7)
    assert ids(7) != ids(8)

def test_the_two_benchmarks_target_different_graphs():
    assert evaluate_qald.BENCHMARKS["qald10"].target_kg == "wikidata"
    assert evaluate_qald.BENCHMARKS["qald9plus"].target_kg == "dbpedia"
