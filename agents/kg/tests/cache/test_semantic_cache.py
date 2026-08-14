import pytest

from cache.semantic_cache import SemanticCache
from pipeline import KGPipeline
from translators.base_translator import BaseTranslator
from pruners.base_pruner import PrunedSchema

class _FakeClient:
    model_name = "fake"

class _FakeTranslator(BaseTranslator):
    def translate(self, question, schema_context="", temperature=0.0, top_p=None):
        return "SELECT ?x WHERE { ?x ?p ?o }"

    def generate_feedback_prompt(self, query, schema_context):
        return schema_context

class _FakeConnector:
    def ground_results(self, raw_results):
        return list(raw_results)

class _FakePruner:
    def prune(self, seed_entity_ids, question=""):
        return PrunedSchema(context_text="fake schema")

class _FakeLinker:
    def link(self, text):
        return []

class _FakeProvider:
    """Provider con componenti finti: serve a esercitare la politica di caching senza rete né LLM."""

    def __init__(self, rows):
        class Executor:
            def execute(self, query):
                return list(rows)

        self.connector = _FakeConnector()
        self.translator = _FakeTranslator(llm_client=_FakeClient())
        self.executor = Executor()
        self.pruner = _FakePruner()
        self.corrector = None
        self.linker = _FakeLinker()

@pytest.mark.parametrize(
    "rows, expected_in_cache",
    [([], False), ([{"x": "value"}], True)],
)
def test_only_non_empty_results_are_cached(rows, expected_in_cache):
    """
    Un risultato vuoto può nascere da un guasto transitorio assorbito dai retry: metterlo in
    cache lo renderebbe definitivo per la domanda e per ogni parafrasi sopra soglia.
    """
    cache = SemanticCache()
    pipeline = KGPipeline(provider=_FakeProvider(rows), cache=cache, target_kg="wikidata")
    pipeline.run("Who is the mayor of Rome?")
    assert (cache.get("Who is the mayor of Rome?") is not None) is expected_in_cache

def test_cache_hit_exact():
    cache = SemanticCache(capacity=5)
    cache.set("What is the birth date of Albert Einstein?", "SELECT ?d WHERE {...}", [{"date": "1879-03-14"}], confidence=0.9)
    res = cache.get("What is the birth date of Albert Einstein?")
    assert res is not None
    query, results, confidence = res
    assert results[0]["date"] == "1879-03-14"
    assert confidence == 0.9

def test_cache_hit_paraphrase():
    """domande semanticamente equivalenti devono fare hit anche se il testo è diverso."""
    cache = SemanticCache(capacity=5)
    cache.set("What is the capital of France?", "SELECT ?c WHERE {...}", [{"capital": "Paris"}], confidence=1.0)
    res = cache.get("What's the capital city of France?")
    assert res is not None
    assert res[1][0]["capital"] == "Paris"

def test_cache_miss_different_question():
    """domande diverse (anche se su entità o proprietà correlate) non devono fare hit."""
    cache = SemanticCache(capacity=5)
    cache.set("What is the capital of France?", "SELECT ?c WHERE {...}", [{"capital": "Paris"}])
    assert cache.get("What is the capital of Germany?") is None
    assert cache.get("What is the population of France?") is None

def test_cache_miss():
    cache = SemanticCache(capacity=5)
    assert cache.get("a question that was never cached") is None

def test_count_question_does_not_hit_list_question():
    """Conteggio ed elenco hanno embedding quasi identici (0.9405) ma risposte di natura
    diversa, e nessuna soglia li separa: una vera parafrasi scora 0.9442, appena sopra."""
    cache = SemanticCache()
    cache.set(
        "Which movies did Tom Hanks act in?",
        "MATCH (p:Person {name: 'Tom Hanks'})-[:ACTED_IN]->(m:Movie) RETURN m.title",
        [{"title": "Apollo 13"}, {"title": "Cast Away"}],
    )
    assert cache.get("How many movies did Tom Hanks act in?") is None

def test_list_question_does_not_hit_count_question():
    """la partizione deve valere in entrambe le direzioni."""
    cache = SemanticCache()
    cache.set(
        "How many official languages does Switzerland have?",
        "SELECT (COUNT(?l) AS ?c) WHERE { wd:Q39 wdt:P37 ?l }",
        [{"c": "4"}],
    )
    assert cache.get("What are the official languages of Switzerland?") is None

def test_paraphrase_of_a_count_question_still_hits():
    """due domande di conteggio equivalenti devono continuare a fare hit."""
    cache = SemanticCache()
    cache.set(
        "How many movies did Tom Hanks act in?",
        "MATCH (p:Person {name: 'Tom Hanks'})-[:ACTED_IN]->(m:Movie) RETURN count(m)",
        [{"c": 12}],
    )
    assert cache.get("How many movies has Tom Hanks acted in?") is not None

def test_sequel_number_does_not_hit_the_base_title():
    """Il numero del seguito distingue due film ma non l'embedding: 0.9375 contro una soglia
    di 0.92, mentre una parafrasi vera sta a 0.9567 e nessuna soglia le separa."""
    cache = SemanticCache()
    cache.set("when kung fu panda was released", "SELECT ?d WHERE {...}", [{"d": "2008-06-06"}])
    assert cache.get("when kung fu panda 3 was released") is None

def test_base_title_does_not_hit_the_sequel():
    """La partizione deve valere in entrambe le direzioni."""
    cache = SemanticCache()
    cache.set("when kung fu panda 3 was released", "SELECT ?d WHERE {...}", [{"d": "2016-01-23"}])
    assert cache.get("when kung fu panda was released") is None

def test_different_years_never_share_an_answer():
    """Stesso meccanismo su un qualificatore temporale, dove il numero è l'intera domanda."""
    cache = SemanticCache()
    cache.set("what was the population of France in 2010", "SELECT ?p WHERE {...}", [{"p": "64"}])
    assert cache.get("what was the population of France in 2020") is None

def test_paraphrase_containing_the_same_number_still_hits():
    """La partizione separa numeri diversi, non penalizza le domande che ne contengono uno."""
    cache = SemanticCache()
    cache.set("when was kung fu panda 3 released", "SELECT ?d WHERE {...}", [{"d": "2016-01-23"}])
    assert cache.get("when was kung fu panda 3 released?") is not None

def test_decimals_are_not_split():
    """Con \\d+ e sorted() "3.5" e "5.3" davano la stessa chiave, e la partizione che
    doveva separarli li rimetteva insieme."""
    assert SemanticCache._numeric_tokens("da 3.5 a 5.3") == ("3.5", "5.3")
    assert SemanticCache._numeric_tokens("da 5.3 a 3.5") == ("5.3", "3.5")

def test_a_non_positive_capacity_disables_the_cache():
    """Azzerare la capacità da ambiente è il modo naturale di spegnerla: non deve sollevare."""
    cache = SemanticCache(capacity=0)
    cache.set("when kung fu panda was released", "q", [{"d": "2008"}])
    assert cache.get("when kung fu panda was released") is None

def test_eviction_respects_the_capacity():
    cache = SemanticCache(capacity=1)
    cache.set("when kung fu panda was released", "q1", [{"d": "2008"}])
    cache.set("when kung fu panda 3 was released", "q2", [{"d": "2016"}])
    assert len(cache._entries) == 1
    assert cache.get("when kung fu panda was released") is None

def test_clear_really_empties_the_cache():
    cache = SemanticCache()
    cache.set("a question", "q", [{"x": 1}])
    cache.clear()
    assert cache.get("a question") is None
