from cache.base_cache import BaseCache

class NullCache(BaseCache):
    """Cache disattivata, per le valutazioni: memorizzare falserebbe il punteggio."""

    # serve perché KGPipeline fa `cache or SemanticCache()`: passare None non disattiva
    # nulla, ricade sul default. Su un benchmark con domande simili fra loro un cache hit
    # farebbe rispondere a una domanda con i risultati di un'altra.

    def get(self, question: str) -> None:
        return None

    def set(self, question: str, query: str, results: list[dict], confidence: float = 1.0) -> None:
        return None

    def clear(self) -> None:
        return None
