import pytest
import requests

from connectors.wikidata_connector import WikidataConnector

def is_wikidata_reachable() -> bool:
    """Le prove che interrogano davvero le API vanno saltate, non fatte fallire, senza rete."""
    try:
        return requests.head("https://www.wikidata.org/w/api.php", timeout=3).status_code < 500
    except Exception:
        return False

needs_wikidata = pytest.mark.skipif(not is_wikidata_reachable(), reason="Wikidata non raggiungibile")

@pytest.mark.parametrize(
    "valore, atteso",
    [
        # l'endpoint sparql non antepone il segno, l'api wbgetentities sì: entrambe le forme
        # sono la stessa data e devono arrivare all'utente leggibili
        ("1879-03-14T00:00:00Z", "1879-03-14"),
        ("+1879-03-14T00:00:00Z", "1879-03-14"),
        ("-0044-03-15T00:00:00Z", "-0044-03-15"),
        # non sono date e non vanno toccate
        ("The Matrix", "The Matrix"),
        ("21", "21"),
        ("1879-03-14", "1879-03-14"),
    ],
)
def test_iso_dates_are_made_readable(valore, atteso):
    grounded = WikidataConnector().ground_results([{"v": {"value": valore}}])
    assert grounded[0]["v"] == atteso

@needs_wikidata
def test_search_entity():
    connector = WikidataConnector()
    results = connector.search_entity("universe", limit=5)
    assert len(results) > 0
    assert any(r.id == "Q1" for r in results)

@needs_wikidata
def test_get_entity():
    connector = WikidataConnector()
    entity = connector.get_entity("Q1")
    assert entity.id == "Q1"
    assert entity.label != ""

@needs_wikidata
def test_ground_results():
    connector = WikidataConnector()
    grounded = connector.ground_results([{"person": "http://www.wikidata.org/entity/Q937"}])
    assert len(grounded) == 1
    assert "Albert Einstein" in grounded[0]["person"]

def test_ground_results_date():
    connector = WikidataConnector()
    grounded = connector.ground_results([{"birth_date": "+1879-03-14T00:00:00Z"}])
    assert len(grounded) == 1
    assert grounded[0]["birth_date"] == "1879-03-14"

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

@needs_wikidata
def test_ground_results_keeps_source_uri():
    """L'uri originale va conservato: senza, l'interfaccia non può linkare la fonte."""
    connector = WikidataConnector()
    raw = [{"item": {"value": "http://www.wikidata.org/entity/Q937"},
            "date": {"value": "+1879-03-14T00:00:00Z"}}]
    grounded = connector.ground_results(raw)[0]
    assert grounded["item"] == "Albert Einstein"
    assert grounded["_sources"]["item"] == "http://www.wikidata.org/entity/Q937"
    # i letterali non sono entità e non hanno fonte da linkare
    assert "date" not in grounded["_sources"]

def test_ground_results_without_entities_has_no_sources():
    connector = WikidataConnector()
    grounded = connector.ground_results([{"count": {"value": "42"}}])[0]
    assert grounded == {"count": "42"}
