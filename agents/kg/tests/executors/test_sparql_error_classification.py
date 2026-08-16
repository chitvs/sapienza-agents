"""
Test della classificazione degli errori dell'esecutore SPARQL.
"""

import json
import pytest
import requests
from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

QUERY = "SELECT ?x WHERE { ?x ?p ?o }"

class _FakeResponse:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as err:
            raise requests.exceptions.JSONDecodeError(err.msg, err.doc, err.pos) from None

class _FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests: list[dict] = []

    def post(self, url, data=None, timeout=None):
        self.requests.append({"url": url, "data": data})
        if self.error is not None:
            raise self.error
        return self.response

def build_executor(session) -> SPARQLExecutor:
    executor = SPARQLExecutor(endpoint="http://fake.localhost/sparql", timeout=1.0)
    executor.session = session
    return executor

def test_html_instead_of_json_is_a_retryable_failure():
    executor = build_executor(_FakeSession(_FakeResponse(200, "<html>502 Bad Gateway</html>")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable

def test_a_timeout_is_retryable():
    executor = build_executor(_FakeSession(error=requests.Timeout("too slow")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable

@pytest.mark.parametrize("status, retryable", [(429, True), (503, True), (400, False), (500, False)])
def test_only_some_http_codes_are_transient(status, retryable):
    executor = build_executor(_FakeSession(_FakeResponse(status, "error")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable is retryable

def test_a_write_query_never_reaches_the_network():
    session = _FakeSession(_FakeResponse(200, "{}"))
    executor = build_executor(session)
    with pytest.raises(SPARQLExecutionError):
        executor.execute("INSERT DATA { wd:Q1 rdfs:label 'x' } ; SELECT ?x WHERE { ?x ?p ?o }")
    assert session.requests == []

def test_a_malformed_endpoint_is_reported_and_is_not_retryable():
    executor = SPARQLExecutor(endpoint="dbpedia.org/sparql", timeout=1.0)
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert "endpoint non valido" in str(err.value)
    assert not err.value.retryable

def test_ask_queries_return_the_boolean():
    executor = build_executor(_FakeSession(_FakeResponse(200, '{"boolean": true}')))
    assert executor.execute("ASK { ?x ?p ?o }") == [{"boolean": True}]
