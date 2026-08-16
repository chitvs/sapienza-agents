"""
Test della distinzione fra grafo non raggiungibile e risposta vuota.
"""

import time
import pytest
import requests
from connectors.base_connector import KnowledgeGraphUnavailableError
from connectors.dbpedia_connector import DBpediaConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.wikidata_connector import WikidataConnector

class BrokenSession:
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
    with pytest.raises(KnowledgeGraphUnavailableError):
        Neo4jConnector(executor=BrokenExecutor()).get_schema()

def test_empty_answer_is_not_a_failure():
    class EmptyExecutor:
        def execute_trusted(self, query, params=None):
            return []

    assert Neo4jConnector(executor=EmptyExecutor()).search_entity("inesistente") == []
