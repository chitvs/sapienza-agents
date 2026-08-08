from abc import ABC, abstractmethod
from typing import Any

class BaseExecutor(ABC):
    """Interfaccia degli esecutori di query sui knowledge graph."""

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """Esegue la query e restituisce i risultati grezzi."""
        raise NotImplementedError
