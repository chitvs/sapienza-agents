from connectors.wikimedia_connector import WikimediaConnector

def test_search_entity():
    connector = WikimediaConnector()
    results = connector.search_entity("universe", limit=5)
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

def test_ground_results_date():
    connector = WikimediaConnector()
    grounded = connector.ground_results([{"birth_date": "+1879-03-14T00:00:00Z"}])
    assert len(grounded) == 1
    assert grounded[0]["birth_date"] == "1879-03-14"

def test_bounded_cache():
    connector = WikimediaConnector(max_cache_size=2)
    connector._set_cache_entry(connector._search_cache, "k1", [])
    connector._set_cache_entry(connector._search_cache, "k2", [])
    assert len(connector._search_cache) == 2
    connector._set_cache_entry(connector._search_cache, "k3", [])
    assert len(connector._search_cache) == 2
    assert "k1" not in connector._search_cache
    assert "k3" in connector._search_cache
