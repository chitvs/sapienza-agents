from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class EntityCandidate:
    id: str
    label: str
    description: str | None = None

@dataclass
class EntityData:
    id: str
    label: str
    properties: dict[str, list[str]]

class BaseConnector(ABC):

    @abstractmethod
    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """Cerca entità a partire da testo, ritorna una lista di entità candidate, con un limite."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> EntityData:
        """Recupera i dati completi di un'entita, nota dal suo id."""
        raise NotImplementedError
