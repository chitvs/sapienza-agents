"""
Test della distinzione fra servizio non raggiungibile e risposta vuota.

È la differenza fra dichiarare un guasto e produrre una risposta inventata: se il
connettore restituisse una lista vuota, la pipeline proseguirebbe con uno schema privo
di proprietà e il modello genererebbe una query non ancorata ai dati reali.
"""
import pytest
import requests

from connectors.base_connector import KnowledgeGraphUnavailableError
from connectors.dbpedia_connector import DBpediaConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.wikidata_connector import WikidataConnector

class BrokenSession:
    """Sessione HTTP che simula un endpoint irraggiungibile."""

    def get(self, *args, **kwargs):
        raise requests.ConnectionError("connessione rifiutata")

    def post(self, *args, **kwargs):
        raise requests.ConnectionError("connessione rifiutata")

class BrokenExecutor:
    def execute_trusted(self, query, params=None):
        raise RuntimeError("bolt non raggiungibile")

def test_wikidata_search_declares_the_failure():
    connector = WikidataConnector()
    connector.session = BrokenSession()
    with pytest.raises(KnowledgeGraphUnavailableError) as err:
        connector.search_entity("Albert Einstein")
    assert err.value.kg == "wikidata"

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
