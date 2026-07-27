# Test per il wikimedia connector

from connectors.wikimedia import WikimediaConnector

# test di ricerca, funzione search_entity
# 'universe' corrisponde a Q1
# controlla se effettivamente appare tra i risultati di ricerca
def test_search_entity_finds_known_entity():
    connector = WikimediaConnector()
    results = connector.search_entity("universe", limit=3)

    assert len(results) > 0 # abbiamo almeno 1 risultato?
    assert any(r.id == "Q1" for r in results) # Q1 (il risultato atteso) c'è?

# test di estrazione, funzione get_entity
def test_get_entity_returns_label_and_properties():
    connector = WikimediaConnector()
    entity = connector.get_entity("Q1")

    assert entity.id == "Q1" # l'entity che abbiamo "preso" corrisponde a Q1?
    assert "universe" in entity.label # è universe?
    assert len(entity.properties) > 0 # ha proprietà? ... e quindi è valida?
