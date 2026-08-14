"""
Test del connettore DBpedia.

Qui sta la sola logica pura: escaping degli identificatori e grounding dei risultati.
Ciò che interroga davvero l'endpoint pubblico vive in tests/dbpedia/test_dbpedia_endpoint.py.
"""
import pytest

from connectors.dbpedia_connector import DBpediaConnector

def test_simple_resource_uses_short_form():
    c = DBpediaConnector()
    assert c.format_entity_ref("Albert_Einstein") == "dbr:Albert_Einstein"

@pytest.mark.parametrize("resource", ["Mercury_(planet)", "Princeton,_New_Jersey", "Trois-Rivières"])
def test_resource_with_special_chars_uses_full_uri(resource):
    """
    Parentesi, virgole e lettere accentate non sono ammesse in un nome prefissato SPARQL:
    devono produrre un URI completo, altrimenti la query non è sintatticamente valida.
    """
    ref = DBpediaConnector().format_entity_ref(resource)
    assert ref.startswith("<http://dbpedia.org/resource/")
    assert ref.endswith(">")

def test_highlight_tags_are_stripped():
    """la Lookup API restituisce le etichette con tag <B> attorno ai termini cercati."""
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
    """L'uri originale va conservato accanto all'etichetta leggibile."""
    grounded = DBpediaConnector().ground_results(
        [{"place": {"value": "http://dbpedia.org/resource/Princeton,_New_Jersey"},
          "year": {"value": "1955"}}]
    )[0]
    assert grounded["place"] == "Princeton, New Jersey"
    assert grounded["_sources"]["place"] == "http://dbpedia.org/resource/Princeton,_New_Jersey"
    assert "year" not in grounded["_sources"]
