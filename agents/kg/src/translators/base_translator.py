from abc import ABC, abstractmethod

from configs.settings import settings
from llm import build_llm_client
from shared.ollama_client import OllamaClient

class BaseTranslator(ABC):
    """Interfaccia del traduttore da linguaggio naturale a query sul KG."""

    def __init__(
        self,
        llm_client: OllamaClient | None = None,
        model_name: str | None = None,
        host: str | None = None,
    ) -> None:
        self.llm_client = llm_client or build_llm_client(
            model_name or settings.ollama_translation_model, host=host
        )

    @abstractmethod
    def translate(
        self,
        question: str,
        schema_context: str = "",
        temperature: float = 0.0,
        top_p: float | None = None,
    ) -> str:
        """Traduce la domanda in una query per il KG; i parametri di campionamento servono ai ritentativi."""
        raise NotImplementedError

    @abstractmethod
    def generate_feedback_prompt(self, query: str, schema_context: str) -> str:
        """Genera il prompt di rigenerazione ReAct quando la query non restituisce righe."""
        raise NotImplementedError

    @staticmethod
    def sanitize(query: str) -> str:
        """Normalizza gli errori di forma ricorrenti nell'output dell'LLM."""
        return query

    def postprocess(self, query: str, question: str) -> str:
        """Riparazioni deterministiche dopo la generazione; le sottoclassi le estendono."""
        return query

    @classmethod
    def relax_constraints(cls, query: str) -> str | None:
        """Versione alleggerita da provare quando la query non restituisce righe, o None."""
        return None
