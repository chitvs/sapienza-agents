from typing import Callable

from correctors.base_corrector import BaseCorrector
from llm import build_llm_client
from shared.ollama_client import OllamaClient

class ErrorConditionedCorrector(BaseCorrector):
    """Corregge una query fallita classificando l'errore e ri-promptando l'LLM."""

    def __init__(
        self,
        llm_client: OllamaClient | None = None,
        prompt_filename: str = "correction.txt",
        sanitizer: Callable[[str], str] | None = None,
    ) -> None:
        self.llm_client = llm_client or build_llm_client()
        # prompt e sanitizer sono iniettabili perché dipendono dal linguaggio di query
        self.prompt_filename = prompt_filename
        if sanitizer is not None:
            self.sanitizer = sanitizer
        else:
            from translators.sparql_translator import WikidataSPARQLTranslator

            self.sanitizer = WikidataSPARQLTranslator.sanitize

    def classify_error(self, error_message: str) -> str:
        """Classifica l'errore per scegliere le linee guida di correzione da applicare."""
        err_lower = error_message.lower()
        if any(k in err_lower for k in ("syntax", "parse", "unexpected")):
            return "SYNTAX_ERROR"
        if any(k in err_lower for k in ("prefix", "namespace", "undefined")):
            return "MISSING_PREFIX"
        if any(k in err_lower for k in ("timeout", "time out", "timed out")):
            return "TIMEOUT"
        return "GENERAL_ERROR"

    def correct(self, question: str, failed_query: str, error_message: str, schema_context: str = "") -> str:
        """Rigenera la query fallita a partire dal tipo di errore riscontrato."""
        error_type = self.classify_error(error_message)
        schema_section = f"contesto schema disponibile:\n{schema_context}" if schema_context else ""

        system_prompt = self.llm_client.load_prompt(
            self.prompt_filename,
            question=question,
            failed_query=failed_query,
            error_message=error_message,
            error_type=error_type,
            schema_context=schema_section,
        )
        corrected_raw = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=(
                f"Question: {question}\nError Type: {error_type}\n"
                f"Failed Query: {failed_query}\nError: {error_message}"
            ),
            temperature=0.0,
        )
        return self.sanitizer(OllamaClient.clean_code_block(corrected_raw))
