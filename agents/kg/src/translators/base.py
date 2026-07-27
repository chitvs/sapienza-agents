from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TranslationResult:
    query: str
    raw_output: str

class Translator(ABC):
    """Interfaccia base per i traduttori linguaggio naturale -> kglanguage."""

    @abstractmethod
    def translate(self, question: str, schema_context: str) -> TranslationResult:
        """Traduce una domanda in kglanguage, dato lo schema del grafo."""
        raise NotImplementedError
