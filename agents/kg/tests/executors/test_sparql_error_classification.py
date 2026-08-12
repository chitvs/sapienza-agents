"""
Test della classificazione degli errori dell'esecutore SPARQL.

`retryable` decide se la pipeline ripete la query identica o attiva la self-correction:
sbagliarlo significa ripetere una query rotta, o riscriverne una valida. Si verifica con
una sessione finta, quindi senza rete.
"""
import pytest
import requests

from executors.sparql_executor import SPARQLExecutor, SPARQLExecutionError

QUERY = "SELECT ?x WHERE { ?x ?p ?o }"

class RispostaFinta:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        import json

        return json.loads(self.text)

class SessioneFinta:
    def __init__(self, risposta=None, errore=None):
        self.risposta = risposta
        self.errore = errore
        self.richieste: list[dict] = []

    def post(self, url, data=None, timeout=None):
        self.richieste.append({"url": url, "data": data})
        if self.errore is not None:
            raise self.errore
        return self.risposta

def esecutore(sessione) -> SPARQLExecutor:
    executor = SPARQLExecutor(endpoint="http://finto.localhost/sparql", timeout=1.0)
    executor.session = sessione
    return executor

def test_html_al_posto_del_json_e_un_guasto_ritentabile():
    """Un endpoint sotto carico risponde 200 con una pagina di errore: è transitorio."""
    executor = esecutore(SessioneFinta(RispostaFinta(200, "<html>502 Bad Gateway</html>")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable

def test_il_timeout_e_ritentabile():
    executor = esecutore(SessioneFinta(errore=requests.Timeout("troppo lento")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable

@pytest.mark.parametrize("status, ritentabile", [(429, True), (503, True), (400, False), (500, False)])
def test_solo_alcuni_codici_http_sono_transitori(status, ritentabile):
    """500 è escluso di proposito: Blazegraph lo usa per i timeout di query, che ripetere
    identica non risolve — quella va riscritta dal correttore."""
    executor = esecutore(SessioneFinta(RispostaFinta(status, "errore")))
    with pytest.raises(SPARQLExecutionError) as err:
        executor.execute(QUERY)
    assert err.value.retryable is ritentabile

def test_una_query_di_scrittura_non_raggiunge_mai_la_rete():
    """La guardia deve fermarla prima della POST, non affidarsi al rifiuto dell'endpoint."""
    sessione = SessioneFinta(RispostaFinta(200, "{}"))
    executor = esecutore(sessione)
    with pytest.raises(SPARQLExecutionError):
        executor.execute("INSERT DATA { wd:Q1 rdfs:label 'x' } ; SELECT ?x WHERE { ?x ?p ?o }")
    assert sessione.richieste == []

def test_le_ask_restituiscono_il_booleano():
    executor = esecutore(SessioneFinta(RispostaFinta(200, '{"boolean": true}')))
    assert executor.execute("ASK { ?x ?p ?o }") == [{"boolean": True}]
