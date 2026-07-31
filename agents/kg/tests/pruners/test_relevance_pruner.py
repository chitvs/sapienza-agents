import pytest
from pruners.relevance_pruner import RelevancePruner
from connectors.base_connector import EntityData

class DummyConnector:
    def get_entity(self, entity_id: str) -> EntityData:
        return EntityData(
            id=entity_id,
            label="Real Madrid",
            description="Spanish professional football club",
            properties={
                "P488 (chairperson)": ["Q245207"],
                "P17 (country)": ["Q29"],
                "P571 (inception)": ["1902-03-06"],
                "P641 (sport)": ["Q2736"],
            },
        )

def test_relevance_pruner_scores():
    pruner = RelevancePruner()
    schema = pruner.prune(
        seed_entity_ids=["Q8682"],
        connector_or_client=DummyConnector(),
        question="Chi è il presidente del Real Madrid?",
    )
    assert "P488" in schema.context_text
    assert "Real Madrid" in schema.context_text
    assert len(schema.nodes) == 1
