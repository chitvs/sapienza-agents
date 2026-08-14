"""
Test del percorso a zero righe della pipeline, con componenti finti e senza rete né LLM.

È il punto in cui un guasto dell'endpoint può travestirsi da "il grafo non contiene questo
dato": la differenza non si vede nella risposta, ma cambia il significato di ogni numero
prodotto dai benchmark.
"""
import pytest

from cache.null_cache import NullCache
from connectors.base_connector import KnowledgeGraphUnavailableError
from executors.base_executor import QueryExecutionError
from pipeline import KGPipeline
from pruners.base_pruner import PrunedSchema
from translators.base_translator import BaseTranslator

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
    """Provider finto la cui prima esecuzione riesce a vuoto e le successive sollevano.

    Riproduce lo scenario reale: la query iniziale gira e non trova righe, poi il guasto
    arriva durante il tentativo di recupero, cioè dove veniva silenziosamente ingoiato.
    """

    def __init__(self, error=None):
        outer = self

        class Executor:
            def execute(self, query):
                outer.calls += 1
                if outer.error is not None and outer.calls > 1:
                    raise outer.error
                return []

        self.error = error
        self.calls = 0
        self.connector = _FakeConnector()
        self.translator = _FakeTranslator(llm_client=_FakeClient())
        self.executor = Executor()
        self.pruner = _FakePruner()
        self.corrector = None
        self.linker = _FakeLinker()

def _run(error=None):
    pipeline = KGPipeline(provider=_FakeProvider(error), cache=NullCache(), target_kg="wikidata")
    return pipeline.run("Who directed The Matrix?")

def test_an_empty_graph_answer_is_not_an_error():
    """Zero righe da una query eseguita senza problemi è una risposta legittima."""
    outcome = _run()
    assert outcome.results == []
    assert outcome.confidence == 0.0

def test_an_unreachable_graph_is_not_an_empty_answer():
    """Degradare il guasto a zero righe darebbe 200 con results vuoti, e nel benchmark
    addebiterebbe alla traduzione un problema di rete."""
    with pytest.raises(KnowledgeGraphUnavailableError):
        _run(KnowledgeGraphUnavailableError("wikidata", "connessione rifiutata"))

def test_a_transient_execution_failure_propagates():
    """Se l'endpoint continua a rispondere male dopo i ritentativi, non è una risposta."""
    with pytest.raises(QueryExecutionError):
        _run(QueryExecutionError("HTTP 503", retryable=True))

def test_a_query_the_model_got_wrong_still_degrades_to_zero_rows():
    """Un errore di sintassi non è un guasto: la domanda resta senza risposta, non esplode."""
    outcome = _run(QueryExecutionError("SYNTAX_ERROR", retryable=False))
    assert outcome.results == []
