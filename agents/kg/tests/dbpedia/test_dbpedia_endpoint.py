"""
Test sulla Lookup API e sull'endpoint SPARQL di DBpedia.
"""

import pytest
from conftest import is_dbpedia_reachable
from connectors.dbpedia_connector import DBpediaConnector

requires_dbpedia = pytest.mark.skipif(
    not is_dbpedia_reachable(), reason="endpoint pubblico DBpedia non raggiungibile"
)

@requires_dbpedia
def test_search_entity_live():
    cands = DBpediaConnector().search_entity("Albert Einstein", limit=3)
    assert cands
    assert any(c.id == "Albert_Einstein" for c in cands)

@requires_dbpedia
def test_get_entity_live():
    entity = DBpediaConnector().get_entity("Albert_Einstein")
    assert entity.label == "Albert Einstein"
    assert "birthPlace" in entity.properties

@requires_dbpedia
def test_prominence_is_complete_or_empty():
    connector = DBpediaConnector()
    cands = connector.search_entity("Mercury", limit=5)
    prominence = connector.candidate_prominence(cands)
    assert not prominence or set(prominence) == {c.id for c in cands}
