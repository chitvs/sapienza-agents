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

def test_la_query_corretta_riceve_le_riparazioni_strutturali():
    """Il correttore deve applicare le stesse riparazioni della traduzione: la sua query
    nasce nelle condizioni peggiori ed è quella che ne ha più bisogno."""
    class ClientFinto:
        model_name = "finto"

        def load_prompt(self, prompt_filename, **kwargs):
            return "prompt"

        def chat(self, system_prompt, user_content, temperature=0.0, top_p=None):
            # ?personLabel non è legata nel WHERE: postprocess deve redirigerla su ?person
            return "```sparql\nSELECT ?personLabel WHERE { wd:Q937 wdt:P26 ?person . }\n```"

    corrector = ErrorConditionedCorrector(WikidataSPARQLTranslator(), ClientFinto())
    corretta = corrector.correct(question="chi?", failed_query="SELECT ?x WHERE {}", error_message="boom")
    assert "?personLabel" in corretta

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_correct():
    corrector = ErrorConditionedCorrector(WikidataSPARQLTranslator())
    query = corrector.correct(
        question="Chi è Einstein?",
        failed_query="SELECT * WHERE { wd:Q937 ?p ?o }",
        error_message="Undefined prefix wd:",
    )
    assert isinstance(query, str) and len(query) > 0
