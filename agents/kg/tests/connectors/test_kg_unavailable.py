"""
Test della distinzione fra servizio non raggiungibile e risposta vuota.

È la differenza fra dichiarare un guasto e produrre una risposta inventata: se il
connettore restituisse una lista vuota, la pipeline proseguirebbe con uno schema privo
di proprietà e il modello genererebbe una query non ancorata ai dati reali.
"""
import time

import pytest
import requests

from connectors.base_connector import KnowledgeGraphUnavailableError
from connectors.dbpedia_connector import DBpediaConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.wikidata_connector import WikidataConnector

class BrokenSession:
    """Sessione HTTP che simula un endpoint irraggiungibile, contando i tentativi."""

    def __init__(self):
        self.attempts = 0

    def get(self, *args, **kwargs):
        self.attempts += 1
        raise requests.ConnectionError("connessione rifiutata")

    def post(self, *args, **kwargs):
        self.attempts += 1
        raise requests.ConnectionError("connessione rifiutata")

@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """I connettori attendono fra un tentativo e l'altro: qui l'attesa è tempo speso a
    dormire, e senza neutralizzarla questi due test da soli costavano 30 secondi."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

class BrokenExecutor:
    def execute_trusted(self, query, params=None):
        raise RuntimeError("bolt non raggiungibile")

def test_wikidata_search_declares_the_failure():
    connector = WikidataConnector()
    connector.session = session = BrokenSession()
    with pytest.raises(KnowledgeGraphUnavailableError) as err:
        connector.search_entity("Albert Einstein")
    assert err.value.kg == "wikidata"
    # il guasto va dichiarato dopo aver ritentato, non al primo errore di rete
    assert session.attempts > 1

def test_wikidata_entity_fetch_declares_the_failure():
    connector = WikidataConnector()
    connector.session = BrokenSession()
    with pytest.raises(KnowledgeGraphUnavailableError):
        connector.get_entities(["Q937"])

def test_dbpedia_declares_the_failure():
    connector = DBpediaConnector()
    connector.session = BrokenSession()
    with pytest.raises(KnowledgeGraphUnavailableError) as err:
        connector.search_entity("Albert Einstein")
    assert err.value.kg == "dbpedia"

def test_neo4j_declares_the_failure():
    connector = Neo4jConnector(executor=BrokenExecutor())
    with pytest.raises(KnowledgeGraphUnavailableError) as err:
        connector.search_entity("The Matrix")
    assert err.value.kg == "neo4j"

def test_neo4j_schema_failure_is_not_silent():
    """Senza schema il modello non saprebbe quali relazioni esistono nel grafo."""
    with pytest.raises(KnowledgeGraphUnavailableError):
        Neo4jConnector(executor=BrokenExecutor()).get_schema()

def test_empty_answer_is_not_a_failure():
    """Una risposta legittimamente vuota resta vuota e non solleva."""
    class EmptyExecutor:
        def execute_trusted(self, query, params=None):
            return []

    assert Neo4jConnector(executor=EmptyExecutor()).search_entity("inesistente") == []
