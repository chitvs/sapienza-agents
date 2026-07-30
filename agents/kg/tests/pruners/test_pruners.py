from pruners.khop_pruner import KHopPruner
from connectors.wikimedia_connector import WikimediaConnector

def test_khop_prune():
    connector = WikimediaConnector()
    res = KHopPruner().prune(seed_entity_ids=["Q937"], connector_or_client=connector)
    assert "Albert Einstein" in res.context_text or "Q937" in res.context_text
