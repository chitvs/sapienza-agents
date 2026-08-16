"""
Test dei prefissi con cui lo schema viene citato all'LLM.
"""

from connectors.dbpedia_connector import DBpediaConnector
from connectors.wikidata_connector import WikidataConnector
from pruners.vector_pruner import VectorPruner

CLASS = {"id": "Mountain", "label": "mountain", "description": "a large landform"}

def test_dbpedia_classes_are_cited_with_the_ontology_prefix():
    line = VectorPruner._describe(CLASS, DBpediaConnector.class_prefix)
    assert line.strip().startswith("dbo:Mountain")
    assert "dbr:" not in line

def test_wikidata_classes_stay_in_the_entity_namespace():
    line = VectorPruner._describe({"id": "Q8502", "label": "mountain"}, WikidataConnector.class_prefix)
    assert line.strip().startswith("wd:Q8502")

def test_properties_and_classes_use_different_prefixes_on_dbpedia():
    assert DBpediaConnector.property_prefix == "dbo:"
    assert DBpediaConnector.class_prefix == "dbo:"
    assert DBpediaConnector.entity_prefix == "dbr:"
