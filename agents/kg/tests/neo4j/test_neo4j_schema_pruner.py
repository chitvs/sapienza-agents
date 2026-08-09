"""
Test dello schema pruner Neo4j con un connettore finto.

Girano senza istanza Neo4j: verificano che lo schema introspezionato venga tradotto in
un contesto testuale corretto per l'llm, in particolare che le direzioni delle relazioni
siano rese esplicitamente, dato che sbagliare direzione e' la causa piu' comune di query
Cypher che eseguono senza errori ma restituiscono zero righe.
"""
from connectors.base_connector import EntityData
from pruners.neo4j_schema_pruner import Neo4jSchemaPruner

class FakeNeo4jConnector:
    entity_prefix = ""
    property_prefix = ""

    def get_schema(self):
        return {
            "labels": {
                "Person": [
                    {"name": "born", "type": "INTEGER"},
                    {"name": "name", "type": "STRING"},
                ],
                "Movie": [
                    {"name": "released", "type": "INTEGER"},
                    {"name": "tagline", "type": "STRING"},
                    {"name": "title", "type": "STRING"},
                ],
            },
            "relationships": [
                {"from": "Person", "type": "ACTED_IN", "to": "Movie"},
                {"from": "Person", "type": "DIRECTED", "to": "Movie"},
            ],
        }

    def get_entity(self, entity_id: str) -> EntityData:
        return EntityData(
            id=entity_id,
            label="Tom Hanks",
            description="Person",
            properties={"name": ["Tom Hanks"], "-[:ACTED_IN]->": ["Apollo 13", "Cast Away"]},
        )

def test_schema_is_fully_listed():
    schema = Neo4jSchemaPruner().prune(seed_entity_ids=[], connector_or_client=FakeNeo4jConnector())
    text = schema.context_text

    assert "(:Person)" in text
    assert "(:Movie)" in text
    # le proprieta' di ogni label devono essere elencate, sono cio' che l'llm puo' usare in RETURN
    assert "title" in text
    assert "born" in text

def test_property_types_are_shown():
    """
    Senza il tipo, il modello puo' scrivere filtri assurdi (es. {released: true} su una
    proprieta' intera) che producono zero righe da una query sintatticamente valida.
    """
    schema = Neo4jSchemaPruner().prune(seed_entity_ids=[], connector_or_client=FakeNeo4jConnector())
    assert "released: INTEGER" in schema.context_text
    assert "title: STRING" in schema.context_text

def test_properties_without_types_still_render():
    """il pruner deve funzionare anche con connettori che non espongono i tipi."""

    class NoTypesConnector(FakeNeo4jConnector):
        def get_schema(self):
            return {"labels": {"Movie": ["title", "released"]}, "relationships": []}

    schema = Neo4jSchemaPruner().prune(seed_entity_ids=[], connector_or_client=NoTypesConnector())
    assert "title" in schema.context_text

def test_relationship_direction_is_explicit():
    schema = Neo4jSchemaPruner().prune(seed_entity_ids=[], connector_or_client=FakeNeo4jConnector())
    assert "(:Person)-[:ACTED_IN]->(:Movie)" in schema.context_text
    assert "(:Person)-[:DIRECTED]->(:Movie)" in schema.context_text

def test_seed_entities_are_included():
    schema = Neo4jSchemaPruner().prune(
        seed_entity_ids=["node-1"], connector_or_client=FakeNeo4jConnector()
    )
    assert "Tom Hanks" in schema.context_text

def test_missing_connector_does_not_crash():
    """senza connettore il pruner deve restituire un contesto vuoto, non sollevare."""
    schema = Neo4jSchemaPruner().prune(seed_entity_ids=["x"], connector_or_client=None)
    assert schema.context_text == ""
