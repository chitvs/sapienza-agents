import re
from typing import Any

class SemanticQueryCache:
    """cache semantica in-memory per memorizzare e recuperare le query generate per domande simili."""

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._cache: dict[str, dict[str, Any]] = {}

    def _normalize_key(self, text: str) -> str:
        """normalizza la stringa della domanda rimovendo punteggiatura e convertendo in minuscolo."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return " ".join(text.split())

    def get(self, question: str) -> tuple[str, list[dict]] | None:
        """restituisce la tupla (query_generata, risultati) se la domanda è presente in cache."""
        key = self._normalize_key(question)
        if key in self._cache:
            entry = self._cache[key]
            return entry["query"], entry["results"]
        return None

    def set(self, question: str, query: str, results: list[dict]):
        """memorizza la query e i risultati per la domanda specificata."""
        key = self._normalize_key(question)
        if key not in self._cache and len(self._cache) >= self.capacity:
            # rimuovi il primo elemento in stile FIFO
            first_key = next(iter(self._cache))
            del self._cache[first_key]

        self._cache[key] = {
            "query": query,
            "results": results,
        }

    def clear(self):
        """svuota la cache semantica."""
        self._cache.clear()
