from cache.base_cache import BaseCache

class NullCache(BaseCache):
    """Cache disattivata, per i benchmark."""

    def get(self, question: str) -> tuple[str, list[dict], float] | None:
        return None

    def set(self, question: str, query: str, results: list[dict], confidence: float = 1.0) -> None:
        return None

    def clear(self) -> None:
        return None
