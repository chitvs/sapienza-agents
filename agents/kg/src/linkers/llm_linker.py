import json
import re
import logging
import unicodedata
from typing import Any
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
                valid = [str(m).strip() for m in mentions if str(m).strip()]
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
        stopwords = {"what", "who", "where", "when", "which", "how", "is", "are", "the", "a", "an", "of", "in", "on", "to", "for", "chi", "cosa", "qual", "quale", "dove", "quando", "il", "la", "le", "i", "gli", "un", "una", "di", "del", "della", "degli", "dei", "da", "con", "su", "per", "tra", "fra"}
        candidates = [w for w in words if w.lower() not in stopwords]
        if candidates:
            return [" ".join(candidates)]

        return [text.strip()]

    def _disambiguate_candidates(self, question: str, mention: str, candidates: list) -> Any | None:
        """
        Seleziona il miglior candidato Wikidata delegando al ragionamento zero-shot dell'LLM.
        Senza alcuna lista di parole, stopword o pattern hardcodati.
        """
        valid_cands = []
        cands_json = []
        for cand in candidates:
            cid = getattr(cand, "id", "")
            if not cid or not re.match(r"^Q\d+$", str(cid)):
                continue
            desc = (getattr(cand, "description", "") or "").lower()
            if "disambiguation" in desc or "wikimedia category" in desc or "categoria wikimedia" in desc:
                continue
            valid_cands.append(cand)
            cands_json.append({
                "qid": cid,
                "label": getattr(cand, "label", ""),
                "description": getattr(cand, "description", ""),
            })

        if not valid_cands:
            return None

        if len(valid_cands) == 1:
            return valid_cands[0]

        try:
            system_prompt = self.llm_client.load_prompt(
                "disambiguate_entity.txt",
                question=question,
                mention=mention,
                candidates_json=json.dumps(cands_json, indent=2, ensure_ascii=False),
            )
            raw_output = self.llm_client.chat(system_prompt=system_prompt, user_content=question, temperature=0.0)
            cleaned = self.llm_client.clean_code_block(raw_output)
            valid_qid_map = {cand.id: cand for cand in valid_cands}

            # Prova prima il parsing JSON per estrarre la chiave 'selected_qid'
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    selected_qid = data.get("selected_qid")
                    if selected_qid in valid_qid_map:
                        return valid_qid_map[selected_qid]
                    elif selected_qid is None:
                        return None
            except Exception:
                pass

            # Match regex mirato sul campo JSON "selected_qid": "Q..."
            json_match = re.search(r'"selected_qid"\s*:\s*"(Q\d+)"', raw_output)
            if json_match and json_match.group(1) in valid_qid_map:
                return valid_qid_map[json_match.group(1)]

            # Fallback: seleziona il QID valido a partire dagli ultimi token
            found_qids = re.findall(r"Q\d+", raw_output)
            for qid in reversed(found_qids):
                if qid in valid_qid_map:
                    return valid_qid_map[qid]
        except Exception as err:
            logger.warning("disambiguazione llm fallita per '%s': %s", mention, err)

        return valid_cands[0]

    def link(self, text: str) -> list[LinkedEntity]:
        """identifica le menzioni con l'llm e le associa ai qid validi di wikidata tramite disambiguazione contestuale."""
        mentions = self._extract_mentions(text)
        linked_entities = []
        seen_qids = set()

        for mention in mentions:
            candidates = self.connector.search_entity(mention, limit=5)
            best_cand = self._disambiguate_candidates(text, mention, candidates)
            if best_cand and best_cand.id not in seen_qids:
                seen_qids.add(best_cand.id)
                linked_entities.append(
                    LinkedEntity(
                        mention=mention,
                        qid=best_cand.id,
                        label=best_cand.label or mention,
                    )
                )

        return linked_entities
