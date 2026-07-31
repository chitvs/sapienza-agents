from shared.ollama_client import OllamaClient
from translators.sparql_translator import SPARQLTranslator

class ErrorConditionedCorrector:
    """correttore guidato da classificazione errori e re-prompting llm."""

    def __init__(self, llm_client: OllamaClient | None = None):
        self.llm_client = llm_client or OllamaClient()

    def classify_error(self, error_message: str) -> str:
        """classifica la tipologia di errore riscontrata."""
        err_lower = error_message.lower()
        if "syntax" in err_lower or "parse" in err_lower or "unexpected" in err_lower:
            return "SYNTAX_ERROR"
        elif "prefix" in err_lower or "namespace" in err_lower or "undefined" in err_lower:
            return "MISSING_PREFIX"
        elif "timeout" in err_lower or "time out" in err_lower or "timed out" in err_lower:
            return "TIMEOUT"
        else:
            return "GENERAL_ERROR"

    def correct(self, question: str, failed_query: str, error_message: str) -> str:
        """corregge la query fallita caricando il prompt di correzione con la tipologia di errore."""
        error_type = self.classify_error(error_message)
        system_prompt = self.llm_client.load_prompt(
            "correction.txt",
            question=question,
            failed_query=failed_query,
            error_message=error_message,
            error_type=error_type,
        )

        corrected_raw = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=f"Domanda: {question}\nTipologia Errore: {error_type}\nQuery Errata: {failed_query}\nErrore: {error_message}",
            temperature=0.0,
        )
        cleaned = OllamaClient.clean_code_block(corrected_raw)
        return SPARQLTranslator.sanitize_sparql(cleaned)
