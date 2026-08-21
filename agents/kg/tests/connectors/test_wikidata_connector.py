"""
Test del connettore Wikidata.
"""

import pytest
from connectors.wikidata_connector import WikidataConnector

@pytest.mark.parametrize(
    "value, expected",
    [
        ("1879-03-14T00:00:00Z", "1879-03-14"),
        ("+1879-03-14T00:00:00Z", "1879-03-14"),
        ("-0044-03-15T00:00:00Z", "-0044-03-15"),
        ("The Matrix", "The Matrix"),
        ("21", "21"),
        ("1879-03-14", "1879-03-14"),
    ],
)
def test_iso_dates_are_made_readable(value, expected):
    grounded = WikidataConnector().ground_results([{"v": {"value": value}}])
    assert grounded[0]["v"] == expected

def test_bounded_cache():
    connector = WikidataConnector()
    connector.max_cache_size = 2
    connector._set_cache_entry(connector._search_cache, "k1", [])
    connector._set_cache_entry(connector._search_cache, "k2", [])
    assert len(connector._search_cache) == 2
    connector._set_cache_entry(connector._search_cache, "k3", [])
    assert len(connector._search_cache) == 2
    assert "k1" not in connector._search_cache
    assert "k3" in connector._search_cache

def test_ground_results_without_entities_has_no_sources():
    connector = WikidataConnector()
    grounded = connector.ground_results([{"count": {"value": "42"}}])[0]
    assert grounded == {"count": "42"}
