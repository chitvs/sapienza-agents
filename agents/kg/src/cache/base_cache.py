from abc import ABC, abstractmethod

class BaseCache(ABC):
    """Interfaccia della cache delle risposte, l'ultimo componente sostituibile della pipeline."""

    @abstractmethod
    def get(self, question: str) -> tuple[str, list[dict], float] | None:
        """Restituisce query, risultati e confidenza memorizzati, o None se non c'è riscontro."""
        raise NotImplementedError

    @abstractmethod
    def set(self, question: str, query: str, results: list[dict], confidence: float = 1.0) -> None:
        """Memorizza l'esito di una domanda."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Svuota la cache."""
        raise NotImplementedError
