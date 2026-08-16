"""
Test del connettore DBpedia.
"""

import pytest
from connectors.dbpedia_connector import DBpediaConnector

def test_simple_resource_uses_short_form():
    c = DBpediaConnector()
    assert c.format_entity_ref("Albert_Einstein") == "dbr:Albert_Einstein"

@pytest.mark.parametrize("resource", ["Mercury_(planet)", "Princeton,_New_Jersey", "Trois-Rivières"])
def test_resource_with_special_chars_uses_full_uri(resource):
    ref = DBpediaConnector().format_entity_ref(resource)
    assert ref.startswith("<http://dbpedia.org/resource/")
    assert ref.endswith(">")

def test_highlight_tags_are_stripped():
    assert DBpediaConnector._strip_highlight("<B>Albert</B> <B>Einstein</B>") == "Albert Einstein"

def test_local_name_and_readable():
    c = DBpediaConnector()
    assert c._local_name("http://dbpedia.org/resource/Princeton,_New_Jersey") == "Princeton,_New_Jersey"
    assert c._readable("Princeton,_New_Jersey") == "Princeton, New Jersey"

def test_ground_results_converts_uris_to_readable_names():
    c = DBpediaConnector()
    raw = [{"birthPlace": {"value": "http://dbpedia.org/resource/Princeton,_New_Jersey"}},
           {"birthPlace": {"value": "1879-03-14"}}]
    grounded = c.ground_results(raw)
    assert grounded[0]["birthPlace"] == "Princeton, New Jersey"
    assert grounded[1]["birthPlace"] == "1879-03-14"

def test_ground_results_keeps_source_uri():
    grounded = DBpediaConnector().ground_results(
        [{"place": {"value": "http://dbpedia.org/resource/Princeton,_New_Jersey"},
          "year": {"value": "1955"}}]
    )[0]
    assert grounded["place"] == "Princeton, New Jersey"
    assert grounded["_sources"]["place"] == "http://dbpedia.org/resource/Princeton,_New_Jersey"
    assert "year" not in grounded["_sources"]
