from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class PrunedSchema:
    context_text: str = ""

class BasePruner(ABC):
    """Seleziona la porzione di schema del KG da passare all'LLM."""

    @staticmethod
    def _prefixes(connector: Any) -> tuple[str, str]:
        """Legge dal connector i prefissi di entità e proprietà del KG in uso."""
        return (
            getattr(connector, "entity_prefix", ""),
            getattr(connector, "property_prefix", ""),
        )

    @abstractmethod
    def prune(
        self,
        seed_entity_ids: list[str],
        connector: Any = None,
        max_items: int = 40,
        question: str = "",
    ) -> PrunedSchema:
        """Estrae e formatta il contesto di schema per l'LLM."""
        raise NotImplementedError
