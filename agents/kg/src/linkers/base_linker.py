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
        """estrae e associa le entità menzionate nel testo ai rispettivi qid."""
        raise NotImplementedError
