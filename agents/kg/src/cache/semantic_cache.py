import re
from typing import Any

import numpy as np

from embeddings import get_embedding_model

# Marcatori di domanda aggregata: identificano la forma della risposta attesa (un numero),
# non l'argomento, quindi restano validi su qualunque knowledge graph.
_AGGREGATION_MARKERS = (
    r"how many", r"how much", r"the number of", r"count of", r"total number",
    r"quanti", r"quante", r"numero di",
)

class SemanticQueryCache:
    """Cache in-memory che riconosce domande parafrasate confrontando gli embedding."""

    def __init__(self, capacity: int = 100, similarity_threshold: float = 0.92) -> None:
        self.capacity = capacity
        self.similarity_threshold = similarity_threshold
        self._entries: list[dict[str, Any]] = []

    @staticmethod
    def _is_aggregation_question(question: str) -> bool:
        """Indica se la domanda chiede un conteggio anziché un elenco o un valore."""
        normalized = re.sub(r"\s+", " ", (question or "").lower())
        return any(re.search(marker, normalized) for marker in _AGGREGATION_MARKERS)

    def _embed(self, text: str) -> np.ndarray:
        model = get_embedding_model()
        vec = model.encode([text], convert_to_numpy=True)[0]
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _find_match(self, embedding: np.ndarray, is_aggregation: bool) -> dict[str, Any] | None:
        best_entry: dict[str, Any] | None = None
        best_sim = -1.0
        for entry in self._entries:
            # Partizione rigida per intento: "quanti film" e "quali film" distano 0.9405,
            # mentre una vera parafrasi ne dista 0.9442. Nessuna soglia può separarli,
            # quindi domande con intento diverso non sono mai equivalenti.
            if entry["is_aggregation"] != is_aggregation:
                continue
            sim = float(np.dot(embedding, entry["embedding"]))
            if sim > best_sim:
                best_entry, best_sim = entry, sim
        if best_entry is not None and best_sim >= self.similarity_threshold:
            return best_entry
        return None

    def get(self, question: str) -> tuple[str, list[dict], float] | None:
        """Restituisce (query, risultati, confidence) della domanda più simile sopra soglia."""
        if not self._entries:
            return None
        match = self._find_match(self._embed(question), self._is_aggregation_question(question))
        if match is None:
            return None
        return match["query"], match["results"], match["confidence"]

    def set(self, question: str, query: str, results: list[dict], confidence: float = 1.0) -> None:
        """Memorizza l'esito, aggiornando la voce esistente se la domanda era già in cache."""
        embedding = self._embed(question)
        is_aggregation = self._is_aggregation_question(question)

        existing = self._find_match(embedding, is_aggregation)
        if existing is not None:
            existing.update(
                question=question,
                embedding=embedding,
                query=query,
                results=results,
                confidence=confidence,
            )
            return

        if len(self._entries) >= self.capacity:
            self._entries.pop(0) # FIFO

        self._entries.append({
            "question": question,
            "embedding": embedding,
            "is_aggregation": is_aggregation,
            "query": query,
            "results": results,
            "confidence": confidence,
        })

    def clear(self) -> None:
        """Svuota la cache."""
        self._entries.clear()
