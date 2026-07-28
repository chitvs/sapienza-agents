from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TranslationResult:
    query: str
    raw_output: str

class BaseTranslator(ABC):

    @abstractmethod
    def translate(self, question: str, schema_context: str) -> TranslationResult:
        """Traduce una domanda in linguaggio naturale in una query per il knowledge graph, dato lo schema del grafo."""
        raise NotImplementedError
