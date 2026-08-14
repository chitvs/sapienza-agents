"""
Test dei prefissi con cui lo schema viene citato all'LLM.

Non è formattazione: il prefisso sbagliato produce una query sintatticamente valida che
restituisce zero righe, quindi nessun errore attiva la self-correction e la domanda è persa
senza che nulla lo segnali.
"""
from connectors.dbpedia_connector import DBpediaConnector
from connectors.wikidata_connector import WikidataConnector
from pruners.vector_pruner import VectorPruner

CLASS = {"id": "Mountain", "label": "mountain", "description": "a large landform"}

def test_dbpedia_classes_are_cited_with_the_ontology_prefix():
    """Su DBpedia le classi stanno in dbo:, le risorse in dbr:. `dbr:Mountain` esiste
    davvero (è la pagina "Mountain"), quindi l'errore non si manifesta come errore."""
    line = VectorPruner._describe(CLASS, DBpediaConnector.class_prefix)
    assert line.strip().startswith("dbo:Mountain")
    assert "dbr:" not in line

def test_wikidata_classes_stay_in_the_entity_namespace():
    """Su Wikidata le classi sono Q-id come tutto il resto: qui il prefisso coincide."""
    line = VectorPruner._describe({"id": "Q8502", "label": "mountain"}, WikidataConnector.class_prefix)
    assert line.strip().startswith("wd:Q8502")

def test_properties_and_classes_use_different_prefixes_on_dbpedia():
    """L'invariante che era stata violata: le due famiglie non condividono il namespace."""
    assert DBpediaConnector.property_prefix == "dbo:"
    assert DBpediaConnector.class_prefix == "dbo:"
    assert DBpediaConnector.entity_prefix == "dbr:"
