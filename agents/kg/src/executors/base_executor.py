from abc import ABC, abstractmethod
from typing import Any

# classe di eccezione custom
class QueryExecutionError(Exception):
    """Errore nella validazione o nell'esecuzione di una query sul knowledge graph."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        # retryable distingue un guasto transitorio dell'endpoint da una query sbagliata:
        # sul primo la pipeline ripete identico, sul secondo attiva la self-correction
        self.retryable = retryable

class BaseExecutor(ABC):
    """Interfaccia degli esecutori di query sui knowledge graph."""

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """Esegue la query e restituisce i risultati grezzi."""
        raise NotImplementedError
