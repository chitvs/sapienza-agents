import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class LlmResponseCorrector:
    """correttore per risposte LLM non valide: riprova con feedback sull'errore.

    Quando il LLM restituisce una risposta che non è JSON valido,
    il correttore ri-prompta il modello con la risposta fallita e l'errore,
    chiedendo di riprovare. Riprova fino a max_retries volte.
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def extract_json_with_retry(
        self,
        llm_generate_fn: Callable[[str], str],
        clean_json_fn: Callable[[str], str],
        original_prompt: str,
        failed_response: str,
    ) -> dict | None:
        """riprova l'estrazione JSON fino a max_retries volte con feedback.

        Args:
            llm_generate_fn: funzione che chiama il LLM con un prompt e restituisce la risposta.
            clean_json_fn: funzione che pulisce la risposta (rimuove blocchi markdown).
            original_prompt: il prompt originale che ha generato la risposta fallita.
            failed_response: la risposta del LLM che non è stata parsabile.

        Returns:
            dizionario parsato dal JSON, oppure None se tutti i retry falliscono.
        """
        last_failed = failed_response

        for attempt in range(self.max_retries):
            correction_prompt = (
                f"Your previous response was not valid JSON and could not be parsed.\n"
                f"Previous response: {last_failed}\n\n"
                f"Please respond ONLY with a valid JSON object. "
                f"No explanations, no markdown, no extra text.\n\n"
                f"Original request:\n{original_prompt}"
            )

            raw = llm_generate_fn(correction_prompt)
            cleaned = clean_json_fn(raw)

            try:
                result = json.loads(cleaned)
                logger.info("retry %d/%d riuscito", attempt + 1, self.max_retries)
                return result
            except (json.JSONDecodeError, AttributeError):
                logger.warning(
                    "retry %d/%d fallito: %s",
                    attempt + 1,
                    self.max_retries,
                    cleaned[:100],
                )
                last_failed = raw

        return None
