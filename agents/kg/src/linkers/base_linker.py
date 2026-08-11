from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LinkedEntity:
    mention: str
    id: str
    label: str
    description: str | None = None

class BaseLinker(ABC):
    """Interfaccia dell'entity linker: dal testo agli identificatori del KG."""

    @abstractmethod
    def link(self, text: str) -> list[LinkedEntity]:
        """Estrae le entità menzionate nel testo e le associa ai rispettivi id nel KG."""
        raise NotImplementedError
