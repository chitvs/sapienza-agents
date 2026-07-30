import json
import logging
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import BaseLinker, LinkedEntity
from shared.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

class LLMLinker(BaseLinker):
    """
    entity linker zero-shot basato su llm e wikidata:
    - usa l'llm per identificare ed estrarre le menzioni nel testo in qualsiasi lingua.
    - esegue la ricerca dei candidati su wikidata via api rest.
    """

    def __init__(
        self,
        connector: WikimediaConnector | None = None,
        llm_client: OllamaClient | None = None,
        model_name: str | None = None,
    ):
        self.connector = connector or WikimediaConnector()
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = OllamaClient(model_name=model_name)

    def _extract_mentions(self, text: str) -> list[str]:
        system_prompt = self.llm_client.load_prompt("extract_mentions.txt")
        try:
            raw_output = self.llm_client.chat(system_prompt=system_prompt, user_content=text, temperature=0.0)
            cleaned = self.llm_client.clean_code_block(raw_output)
            mentions = json.loads(cleaned)
            if isinstance(mentions, list):
                return [str(m).strip() for m in mentions if str(m).strip()]
        except Exception as err:
            logger.warning("estrazione menzioni llm fallita: %s", err)

        return [text.strip()]

    def link(self, text: str) -> list[LinkedEntity]:
        """identifica le menzioni con l'llm e le associa ai qid di wikidata."""
        mentions = self._extract_mentions(text)
        linked_entities = []

        for mention in mentions:
            candidates = self.connector.search_entity(mention, limit=5)
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
