from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LinkedEntity:
    mention: str
    qid: str
    label: str
    description: str | None = None

class BaseLinker(ABC):

    @abstractmethod
    def link(self, text: str) -> list[LinkedEntity]:
        """Estrae e associa le entità menzionate nel testo ai rispettivi QID."""
        raise NotImplementedError
