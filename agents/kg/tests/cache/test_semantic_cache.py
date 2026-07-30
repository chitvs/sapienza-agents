from cache.semantic_cache import SemanticQueryCache

def test_cache_hit():
    cache = SemanticQueryCache(capacity=5)
    cache.set("Qual è la data di nascita di Albert Einstein?", "SELECT ?d WHERE {...}", [{"date": "1879-03-14"}])
    res = cache.get("qual è la data di nascita di albert einstein?")
    assert res is not None
    assert res[1][0]["date"] == "1879-03-14"

def test_cache_miss():
    cache = SemanticQueryCache(capacity=5)
    assert cache.get("Domanda non presente") is None
