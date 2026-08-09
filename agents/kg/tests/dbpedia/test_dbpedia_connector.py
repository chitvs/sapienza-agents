"""
Test del connettore DBpedia.

I test sull'escaping degli identificatori girano sempre (sono logica pura); quelli che
interrogano l'endpoint pubblico vengono saltati se non è raggiungibile, perché è un
servizio esterno soggetto a rate limit e a interruzioni.
"""
import pytest
import requests

from connectors.dbpedia_connector import DBpediaConnector

def is_dbpedia_reachable() -> bool:
    try:
        return requests.get("https://dbpedia.org/sparql", timeout=5).status_code < 500
    except Exception:
        return False

requires_dbpedia = pytest.mark.skipif(
    not is_dbpedia_reachable(), reason="endpoint pubblico DBpedia non raggiungibile"
)

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

def test_looks_like_entity_id():
    c = DBpediaConnector()
    assert c.looks_like_entity_id("http://dbpedia.org/resource/Ulm")
    assert c.looks_like_entity_id("dbr:Ulm")
    assert not c.looks_like_entity_id("1879-03-14")

def test_ground_results_converts_uris_to_readable_names():
    c = DBpediaConnector()
    raw = [{"birthPlace": {"value": "http://dbpedia.org/resource/Princeton,_New_Jersey"}},
           {"birthPlace": {"value": "1879-03-14"}}]
    grounded = c.ground_results(raw)
    assert grounded[0]["birthPlace"] == "Princeton, New Jersey"
    assert grounded[1]["birthPlace"] == "1879-03-14"

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

def test_ground_results_keeps_source_uri():
    """L'uri originale va conservato accanto all'etichetta leggibile."""
    grounded = DBpediaConnector().ground_results(
        [{"place": {"value": "http://dbpedia.org/resource/Princeton,_New_Jersey"},
          "year": {"value": "1955"}}]
    )[0]
    assert grounded["place"] == "Princeton, New Jersey"
    assert grounded["_sources"]["place"] == "http://dbpedia.org/resource/Princeton,_New_Jersey"
    assert "year" not in grounded["_sources"]
