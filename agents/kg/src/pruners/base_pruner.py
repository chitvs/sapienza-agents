from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class PrunedSchema:
    context_text: str = ""

class BasePruner(ABC):
    """Seleziona la porzione di schema del KG da passare all'LLM."""

    @staticmethod
    def _prefixes(connector_or_client: Any) -> tuple[str, str]:
        """Legge dal connector i prefissi di entità e proprietà del KG in uso."""
        return (
            getattr(connector_or_client, "entity_prefix", ""),
            getattr(connector_or_client, "property_prefix", ""),
        )

    @abstractmethod
    def prune(
        self,
        seed_entity_ids: list[str],
        connector_or_client: Any = None,
        max_items: int = 40,
        question: str = "",
        max_hops: int = 2,
    ) -> PrunedSchema:
        """Estrae e formatta il contesto di schema per l'LLM."""
        raise NotImplementedError
