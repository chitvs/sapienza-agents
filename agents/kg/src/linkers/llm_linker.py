import json
import ollama
from connectors.base_connector import BaseConnector
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import BaseLinker, LinkedEntity

class LLMLinker(BaseLinker):
    """
    Entity Linker generico basato su LLM (Ollama):
    1. Usa l'LLM per identificare ed estrarre le menzioni di entità nel testo.
    2. Usa il connettore per risolvere ciascuna menzione nel corrispondente QID del grafo.
    """

    def __init__(
        self,
        connector: BaseConnector | None = None,
        model_name: str = "llama3.2",
    ):
        self.connector = connector or WikimediaConnector()
        self.model_name = model_name

    def _extract_mentions(self, text: str) -> list[str]:
        prompt = f"""Estrai tutte le menzioni di entità reali (persone, luoghi, organizzazioni, concetti principali) dalla seguente frase.
Restituisci ESCLUSIVAMENTE un array JSON di stringhe contenente i nomi delle entità estratte.

Esempi:
Frase: "Qual è la data di nascita di Albert Einstein?"
Output: ["Albert Einstein"]

Frase: "Chi ha diretto il film Inception?"
Output: ["Inception"]

Frase: "Quali sono le città principali della Svizzera?"
Output: ["Svizzera"]

Frase: "{text}"
Output:"""

        try:
            response = ollama.generate(model=self.model_name, prompt=prompt)
            raw_output = response.get("response", "").strip()

            # gestione sicura dei blocchi di codice markdown ```json ... ```
            if "```" in raw_output:
                parts = raw_output.split("```")
                for part in parts:
                    part_str = part.strip()
                    if part_str.startswith("json"):
                        part_str = part_str[4:].strip()
                    if part_str.startswith("[") and part_str.endswith("]"):
                        raw_output = part_str
                        break

            mentions = json.loads(raw_output)
            if isinstance(mentions, list):
                return [str(m).strip() for m in mentions if m]
        except Exception:
            pass

        return [text]

    def link(self, text: str) -> list[LinkedEntity]:
        """Identifica le menzioni con l'LLM e risolve i QID tramite il connettore."""
        mentions = self._extract_mentions(text)
        linked_entities = []

        for mention in mentions:
            candidates = self.connector.search_entity(mention, limit=1)
            if candidates:
                best_match = candidates[0]
                linked_entities.append(
                    LinkedEntity(
                        mention=mention,
                        qid=best_match.id,
                        label=best_match.label or mention,
                    )
                )

        return linked_entities
