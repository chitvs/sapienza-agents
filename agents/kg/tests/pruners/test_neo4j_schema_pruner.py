"""
Test dello schema pruner Neo4j con un connettore finto.

Girano senza istanza Neo4j: verificano che lo schema introspezionato venga tradotto in
un contesto testuale corretto per l'llm, in particolare che le direzioni delle relazioni
siano rese esplicitamente, dato che sbagliare direzione è la causa più comune di query
Cypher che eseguono senza errori ma restituiscono zero righe.
"""
from connectors.base_connector import BaseConnector, EntityCandidate, EntityData
from pruners.neo4j_schema_pruner import Neo4jSchemaPruner

class FakeNeo4jConnector(BaseConnector):
    """Deriva da BaseConnector di proposito: un finto duck-typed non riceverebbe i metodi
    concreti della base (get_entities) e mancherebbe il contratto che il pruner usa davvero."""

    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        return []

    def ground_results(self, raw_results):
        return raw_results

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
    schema = Neo4jSchemaPruner(FakeNeo4jConnector()).prune(seed_entity_ids=[])
    text = schema.context_text

    assert "(:Person)" in text
    assert "(:Movie)" in text
    # le proprietà di ogni label devono essere elencate, sono ciò che l'llm può usare in RETURN
    assert "title" in text
    assert "born" in text

def test_property_types_are_shown():
    """
    Senza il tipo, il modello può scrivere filtri assurdi (es. {released: true} su una
    proprietà intera) che producono zero righe da una query sintatticamente valida.
    """
    schema = Neo4jSchemaPruner(FakeNeo4jConnector()).prune(seed_entity_ids=[])
    assert "released: INTEGER" in schema.context_text
    assert "title: STRING" in schema.context_text

def test_relationship_direction_is_explicit():
    schema = Neo4jSchemaPruner(FakeNeo4jConnector()).prune(seed_entity_ids=[])
    assert "(:Person)-[:ACTED_IN]->(:Movie)" in schema.context_text
    assert "(:Person)-[:DIRECTED]->(:Movie)" in schema.context_text

def test_seed_entities_are_included():
    schema = Neo4jSchemaPruner(FakeNeo4jConnector()).prune(seed_entity_ids=["node-1"])
    assert "Tom Hanks" in schema.context_text
