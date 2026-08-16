"""
Test del correttore condizionato dall'errore.
"""

import pytest
from correctors.error_conditioned_corrector import ErrorConditionedCorrector
from translators.sparql_translator import WikidataSPARQLTranslator
from conftest import is_ollama_running

def test_classify_error():
    corrector = ErrorConditionedCorrector(WikidataSPARQLTranslator())
    assert corrector.classify_error("Parse error at line 1") == "SYNTAX_ERROR"
    assert corrector.classify_error("Undefined prefix wd:") == "MISSING_PREFIX"
    assert corrector.classify_error("Request timed out") == "TIMEOUT"
    assert corrector.classify_error("Unknown DB failure") == "GENERAL_ERROR"

def test_the_corrected_query_gets_the_structural_repairs():
    class _FakeClient:
        model_name = "fake"

        def load_prompt(self, prompt_filename, **kwargs):
            return "prompt"

        def chat(self, system_prompt, user_content, temperature=0.0, top_p=None):
            return (
                "```sparql\nSELECT ?cityLabel WHERE "
                "{ wd:Q937 wdt:P26 ?spouse. ?spouse wdt:P19 ?birthPlace. }\n```"
            )

    corrector = ErrorConditionedCorrector(WikidataSPARQLTranslator(), _FakeClient())
    corrected = corrector.correct(
        question="where was einstein's wife born?", failed_query="SELECT ?x WHERE {}", error_message="boom"
    )
    assert "?cityLabel" not in corrected
    assert "?birthPlaceLabel" in corrected

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_correct():
    corrector = ErrorConditionedCorrector(WikidataSPARQLTranslator())
    query = corrector.correct(
        question="Who is Einstein?",
        failed_query="SELECT * WHERE { wd:Q937 ?p ?o }",
        error_message="Undefined prefix wd:",
    )
    assert isinstance(query, str) and len(query) > 0
