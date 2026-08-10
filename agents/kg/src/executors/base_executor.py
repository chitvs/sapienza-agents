from abc import ABC, abstractmethod
from typing import Any

class QueryExecutionError(Exception):
    """Errore nella validazione o nell'esecuzione di una query sul knowledge graph."""

    def __init__(self, message: str, query: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.query = query
        self.retryable = retryable

class BaseExecutor(ABC):
    """Interfaccia degli esecutori di query sui knowledge graph."""

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """Esegue la query e restituisce i risultati grezzi."""
        raise NotImplementedError
