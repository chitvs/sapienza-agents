import pytest
import requests
from correctors.error_conditioned_corrector import ErrorConditionedCorrector

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def test_classify_error():
    corrector = ErrorConditionedCorrector()
    assert corrector.classify_error("Parse error at line 1") == "SYNTAX_ERROR"
    assert corrector.classify_error("Undefined prefix wd:") == "MISSING_PREFIX"
    assert corrector.classify_error("Request timed out") == "TIMEOUT"
    assert corrector.classify_error("Unknown DB failure") == "GENERAL_ERROR"

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_correct():
    corrector = ErrorConditionedCorrector()
    query = corrector.correct(
        question="Chi è Einstein?",
        failed_query="SELECT * WHERE { wd:Q937 ?p ?o }",
        error_message="Undefined prefix wd:",
    )
    assert isinstance(query, str) and len(query) > 0
