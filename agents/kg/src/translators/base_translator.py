from abc import ABC, abstractmethod
from configs.settings import settings
from models.llm import build_llm_client
from shared.ollama_client import OllamaClient

class BaseTranslator(ABC):
    """Interfaccia del traduttore da linguaggio naturale a query sul KG."""

    prompt_filename: str = ""
    correction_prompt_filename: str = ""

    def __init__(self, llm_client: OllamaClient | None = None) -> None:
        self.llm_client = llm_client or build_llm_client(settings.ollama_translation_model)

    def translate(
        self,
        question: str,
        schema_context: str = "",
        temperature: float = 0.0,
        top_p: float | None = None,
    ) -> str:
        """Traduce la domanda in una query per il KG."""
        system_prompt = self.llm_client.load_prompt(
            self.prompt_filename,
            schema=schema_context,
            question=question,
        )
        raw_output = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=question,
            temperature=temperature,
            top_p=top_p,
        )
        return self.repair(OllamaClient.clean_code_block(raw_output), question)

    def repair(self, query: str, question: str) -> str:
        """Applica alla query grezza tutte le riparazioni deterministiche previste dal KG."""
        return self.postprocess(self.sanitize(query), question)

    @abstractmethod
    def generate_feedback_prompt(self, query: str, schema_context: str) -> str:
        """Genera il prompt di rigenerazione ReAct quando la query non restituisce righe."""
        raise NotImplementedError

    @classmethod
    def sanitize(cls, query: str) -> str:
        """Normalizza gli errori di forma ricorrenti nell'output dell'LLM."""
        return query

    def postprocess(self, query: str, question: str) -> str:
        """Riparazioni deterministiche dopo la generazione."""
        return query

    @classmethod
    def relax_constraints(cls, query: str) -> str | None:
        """Versione alleggerita da provare quando la query non restituisce righe, o None."""
        return None
