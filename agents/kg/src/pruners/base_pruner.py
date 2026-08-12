from abc import ABC, abstractmethod
from dataclasses import dataclass

from connectors.base_connector import BaseConnector

@dataclass
class PrunedSchema:
    context_text: str = ""

class BasePruner(ABC):
    """Seleziona la porzione di schema del KG da passare all'LLM."""

    def __init__(self, connector: BaseConnector) -> None:
        self.connector = connector

    @abstractmethod
    def prune(self, seed_entity_ids: list[str], question: str = "") -> PrunedSchema:
        """Estrae e formatta il contesto di schema per l'LLM."""
        raise NotImplementedError
