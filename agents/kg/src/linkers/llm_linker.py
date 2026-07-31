import json
import re
import logging
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import BaseLinker, LinkedEntity
from shared.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

class LLMLinker(BaseLinker):
    """
    entity linker zero-shot basato su llm e wikidata:
    - identifica ed estrae le entità a nome proprio nel testo in qualsiasi lingua.
    - esegue la ricerca dei candidati su wikidata via api rest filtrando le pagine di disambiguazione.
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

    def _extract_proper_nouns(self, text: str) -> list[str]:
        cleaned = re.sub(r"[?!.,;:\'\"]", " ", text)
        words = cleaned.split()
        if not words:
            return []

        sentence_starters = {"what", "who", "where", "when", "which", "how", "chi", "cosa", "qual", "quale", "dove", "quando", "perché", "come"}
        groups = []
        current_group = []

        for idx, w in enumerate(words):
            if w and w[0].isupper() and not (idx == 0 and w.lower() in sentence_starters):
                current_group.append(w)
            else:
                if current_group:
                    groups.append(" ".join(current_group))
                    current_group = []
        if current_group:
            groups.append(" ".join(current_group))

        return groups

    def _extract_mentions(self, text: str) -> list[str]:
        system_prompt = self.llm_client.load_prompt("extract_mentions.txt")
        try:
            raw_output = self.llm_client.chat(system_prompt=system_prompt, user_content=text, temperature=0.0)
            cleaned = self.llm_client.clean_code_block(raw_output)
            mentions = json.loads(cleaned)
            if isinstance(mentions, list):
                valid = [str(m).strip() for m in mentions if str(m).strip() and str(m).strip().lower() in text.lower()]
                if valid:
                    return valid
        except Exception as err:
            logger.warning("estrazione menzioni llm fallita: %s", err)

        # Fallback 1: estrazione basata sulle maiuscole (nomi propri)
        proper_nouns = self._extract_proper_nouns(text)
        if proper_nouns:
            return proper_nouns

        # Fallback 2: rimozione stopword generali
        clean_text = re.sub(r"[?!.,;:]", "", text)
        words = clean_text.split()
        stopwords = {"what", "who", "where", "when", "which", "how", "is", "are", "the", "a", "an", "of", "in", "on", "to", "for", "chi", "cosa", "qual", "quale", "dove", "quando", "il", "la", "le", "i", "gli", "un", "una", "di", "del", "della", "degli", "dei", "in", "da", "con", "su", "per", "tra", "fra", "capital", "capitale", "president", "presidente"}
        candidates = [w for w in words if w.lower() not in stopwords]
        if candidates:
            return [" ".join(candidates)]

        return [text.strip()]

    def link(self, text: str) -> list[LinkedEntity]:
        """identifica le menzioni con l'llm e le associa ai qid validi di wikidata."""
        mentions = self._extract_mentions(text)
        linked_entities = []
        seen_qids = set()

        for mention in mentions:
            candidates = self.connector.search_entity(mention, limit=5)
            for cand in candidates:
                if not cand.id or not re.match(r"^Q\d+$", cand.id):
                    continue

                if cand.id in seen_qids:
                    continue

                # salta le pagine di disambiguazione o categorie interne wikidata
                desc = (cand.description or "").lower()
                if "disambiguation" in desc or "wikimedia category" in desc or "categoria wikimedia" in desc:
                    continue

                seen_qids.add(cand.id)
                linked_entities.append(
                    LinkedEntity(
                        mention=mention,
                        qid=cand.id,
                        label=cand.label or mention,
                    )
                )
                break

        return linked_entities
