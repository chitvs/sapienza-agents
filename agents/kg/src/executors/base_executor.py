from abc import ABC, abstractmethod
from typing import Any

class BaseExecutor(ABC):
    """interfaccia astratta base per gli esecutori di query sui knowledge graph."""

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """esegue la query e restituisce i risultati grezzi."""
        raise NotImplementedError
