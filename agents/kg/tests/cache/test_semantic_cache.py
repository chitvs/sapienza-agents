import pytest

from cache.semantic_cache import SemanticQueryCache
from pipeline import KGPipeline
from pruners.base_pruner import PrunedSchema

class _FakeProvider:
    """Provider con componenti finti: serve a esercitare la politica di caching senza rete né LLM."""

    def __init__(self, rows):
        self.rows = rows

    def get_connector(self):
        class Connector:
            def ground_results(self, raw):
                return list(raw)
        return Connector()

    def get_translator(self):
        class Client:
            model_name = "finto"

        class Translator:
            llm_client = Client()

            def translate(self, question, schema_context=""):
                return "SELECT ?x WHERE { ?x ?p ?o }"

            def generate_feedback_prompt(self, query, schema_context, error_context=""):
                return schema_context
        return Translator()

    def get_executor(self):
        rows = self.rows

        class Executor:
            def execute(self, query):
                return list(rows)
        return Executor()

    def get_pruner(self):
        class Pruner:
            def prune(self, seed_entity_ids, connector_or_client=None, max_items=20, question="", max_hops=2):
                return PrunedSchema(context_text="schema finto")
        return Pruner()

    def get_corrector(self):
        return None

    def get_linker(self):
        class Linker:
            def link(self, text):
                return []
        return Linker()

@pytest.mark.parametrize(
    "righe, atteso_in_cache",
    [([], False), ([{"x": "valore"}], True)],
)
def test_only_non_empty_results_are_cached(righe, atteso_in_cache):
    """
    Un risultato vuoto può nascere da un guasto transitorio assorbito dai retry: metterlo in
    cache lo renderebbe definitivo per la domanda e per ogni parafrasi sopra soglia.
    """
    cache = SemanticQueryCache()
    pipeline = KGPipeline(provider=_FakeProvider(righe), cache=cache, target_kg="wikidata")
    pipeline.run("Who is the mayor of Rome?")
    assert (cache.get("Who is the mayor of Rome?") is not None) is atteso_in_cache

def test_cache_hit_exact():
    cache = SemanticQueryCache(capacity=5)
    cache.set("What is the birth date of Albert Einstein?", "SELECT ?d WHERE {...}", [{"date": "1879-03-14"}], confidence=0.9)
    res = cache.get("What is the birth date of Albert Einstein?")
    assert res is not None
    query, results, confidence = res
    assert results[0]["date"] == "1879-03-14"
    assert confidence == 0.9

def test_cache_hit_paraphrase():
    """domande semanticamente equivalenti devono fare hit anche se il testo e' diverso."""
    cache = SemanticQueryCache(capacity=5)
    cache.set("What is the capital of France?", "SELECT ?c WHERE {...}", [{"capital": "Paris"}], confidence=1.0)
    res = cache.get("What's the capital city of France?")
    assert res is not None
    assert res[1][0]["capital"] == "Paris"

def test_cache_miss_different_question():
    """domande diverse (anche se su entita' o proprieta' correlate) non devono fare hit."""
    cache = SemanticQueryCache(capacity=5)
    cache.set("What is the capital of France?", "SELECT ?c WHERE {...}", [{"capital": "Paris"}])
    assert cache.get("What is the capital of Germany?") is None
    assert cache.get("What is the population of France?") is None

def test_cache_miss():
    cache = SemanticQueryCache(capacity=5)
    assert cache.get("Domanda non presente in cache") is None

def test_count_question_does_not_hit_list_question():
    """
    Una domanda di conteggio e la corrispondente domanda di elenco sono quasi identiche
    come embedding (misurate a 0.9405, sopra la soglia di 0.92) ma hanno risposte di
    natura diversa: la cache non deve mai confonderle. Nessuna soglia puo' separarle,
    perche' una vera parafrasi della stessa domanda scora 0.9442 — appena sopra.
    """
    cache = SemanticQueryCache()
    cache.set(
        "Which movies did Tom Hanks act in?",
        "MATCH (p:Person {name: 'Tom Hanks'})-[:ACTED_IN]->(m:Movie) RETURN m.title",
        [{"title": "Apollo 13"}, {"title": "Cast Away"}],
    )
    assert cache.get("How many movies did Tom Hanks act in?") is None

def test_list_question_does_not_hit_count_question():
    """la partizione deve valere in entrambe le direzioni."""
    cache = SemanticQueryCache()
    cache.set(
        "How many official languages does Switzerland have?",
        "SELECT (COUNT(?l) AS ?c) WHERE { wd:Q39 wdt:P37 ?l }",
        [{"c": "4"}],
    )
    assert cache.get("What are the official languages of Switzerland?") is None

def test_paraphrase_of_a_count_question_still_hits():
    """due domande di conteggio equivalenti devono continuare a fare hit."""
    cache = SemanticQueryCache()
    cache.set(
        "How many movies did Tom Hanks act in?",
        "MATCH (p:Person {name: 'Tom Hanks'})-[:ACTED_IN]->(m:Movie) RETURN count(m)",
        [{"c": 12}],
    )
    assert cache.get("How many movies has Tom Hanks acted in?") is not None
