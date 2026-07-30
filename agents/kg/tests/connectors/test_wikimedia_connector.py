from connectors.wikimedia_connector import WikimediaConnector

def test_search_entity():
    connector = WikimediaConnector()
    results = connector.search_entity("universe", limit=3)
    assert len(results) > 0
    assert any(r.id == "Q1" for r in results)

def test_get_entity():
    connector = WikimediaConnector()
    entity = connector.get_entity("Q1")
    assert entity.id == "Q1"
    assert entity.label != ""

def test_ground_results():
    connector = WikimediaConnector()
    grounded = connector.ground_results([{"person": "http://www.wikidata.org/entity/Q937"}])
    assert len(grounded) == 1
    assert "Albert Einstein" in grounded[0]["person"]
