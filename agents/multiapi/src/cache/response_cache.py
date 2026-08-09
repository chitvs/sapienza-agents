import re
from typing import Any


class ResponseCache:
    """cache in-memory per memorizzare i risultati delle query multiapi.

    Normalizza la domanda (minuscolo, senza punteggiatura) come chiave.
    Quando la cache è piena, rimuove l'elemento più vecchio in stile FIFO.
    Stesso pattern di SemanticQueryCache dell'agente KG.
    """

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._cache: dict[str, dict[str, Any]] = {}

    def _normalize_key(self, text: str) -> str:
        """normalizza la stringa della domanda: minuscolo, rimuovi punteggiatura, collassa spazi."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return " ".join(text.split())

    def get(self, question: str) -> dict[str, Any] | None:
        """restituisce {"intent": str, "results": list[dict]} se la domanda è in cache."""
        key = self._normalize_key(question)
        return self._cache.get(key)

    def set(self, question: str, intent: str, results: list[dict]):
        """memorizza intent e risultati per la domanda specificata."""
        key = self._normalize_key(question)
        if key not in self._cache and len(self._cache) >= self.capacity:
            # rimuovi il primo elemento inserito (FIFO)
            first_key = next(iter(self._cache))
            del self._cache[first_key]

        self._cache[key] = {
            "intent": intent,
            "results": results,
        }

    def clear(self):
        """svuota la cache."""
        self._cache.clear()
