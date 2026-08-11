from abc import ABC, abstractmethod

class BaseTranslator(ABC):
    """Interfaccia del traduttore da linguaggio naturale a query sul KG."""

    @abstractmethod
    def translate(self, question: str, schema_context: str = "") -> str:
        """Traduce la domanda in una query per il KG."""
        raise NotImplementedError

    @abstractmethod
    def generate_feedback_prompt(self, query: str, schema_context: str, error_context: str = "") -> str:
        """Genera il prompt di rigenerazione ReAct quando la query non restituisce righe."""
        raise NotImplementedError
