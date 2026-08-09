import json
import logging
import re
from typing import Any

from connectors.base_connector import BaseConnector, EntityCandidate
from linkers.base_linker import BaseLinker, LinkedEntity
from linkers.gliner_extractor import extract_entity_mentions
from shared.ollama_client import OllamaClient
from configs.settings import settings

logger = logging.getLogger(__name__)

# parole che, pur maiuscole a inizio frase, non sono nomi propri
_SKIP_WORDS = {
    "what", "where", "who", "when", "which", "how",
    "was", "were", "is", "are", "in", "the", "of", "a", "an",
    "does", "did", "do", "has", "have", "had", "can", "could",
    "will", "would", "shall", "should",
}

class LLMLinker(BaseLinker):
    """Entity linker zero-shot: GLiNER estrae le menzioni, l'LLM le disambigua."""

    def __init__(
        self,
        connector: BaseConnector | None = None,
        llm_client: OllamaClient | None = None,
        model_name: str | None = None,
    ) -> None:
        if connector is None:
            from connectors.wikimedia_connector import WikimediaConnector

            connector = WikimediaConnector()
        self.connector = connector

        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = OllamaClient(
                host=settings.ollama_host,
                model_name=model_name or settings.ollama_linking_model,
                timeout=settings.ollama_timeout,
                prompts_dir=settings.prompts_dir,
            )

    def _extract_mentions(self, text: str) -> list[str]:
        """Estrae le menzioni di entità, con fallback progressivi se GLiNER non produce nulla."""
        try:
            candidates = extract_entity_mentions(text)
            if candidates:
                filtered = self._filter_entity_candidates(text, candidates)
                if filtered:
                    return filtered
        except Exception as err:
            logger.warning("estrazione/filtro menzioni gliner fallita: %s", err)

        proper_nouns = self._fallback_extract_proper_nouns(text)
        if proper_nouns:
            return proper_nouns

        clean_text = re.sub(r"[?!.,;:]", "", text).strip()
        return [clean_text] if clean_text else []

    def _filter_entity_candidates(self, question: str, candidates: list[str]) -> list[str]:
        """Scarta dai candidati GLiNER i ruoli e gli attributi generici, tenendo le entità nominate."""
        # GLiNER estrae "president" o "hometown" con score paragonabile a entità vere e
        # nessuna soglia li separa; l'LLM sceglie un sottoinsieme dei candidati estratti,
        # quindi anche sbagliando non può introdurre entità inesistenti nel testo
        if len(candidates) == 1:
            return candidates
        try:
            system_prompt = self.llm_client.load_prompt(
                "filter_entity_mentions.txt",
                question=question,
                spans_json=json.dumps(candidates, ensure_ascii=False),
            )
            raw_output = self.llm_client.chat(
                system_prompt=system_prompt, user_content=question, temperature=0.0
            )
            filtered = json.loads(self.llm_client.clean_code_block(raw_output))
            if isinstance(filtered, list):
                valid = {c.lower() for c in candidates}
                kept = [f for f in filtered if isinstance(f, str) and f.lower() in valid]
                if kept:
                    return kept
        except Exception as err:
            logger.warning("filtro menzioni llm fallito: %s", err)
        return candidates

    @staticmethod
    def _normalize_mention(mention: str) -> str:
        """Rimuove il suffisso possessivo da una menzione ("Shakespeare's" -> "Shakespeare")."""
        return re.sub(r"['’ʼ]s?$", "", mention).strip()

    def _fallback_extract_proper_nouns(self, text: str) -> list[str]:
        """Estrae i nomi propri raggruppando le parole maiuscole consecutive."""
        words = re.sub(r"[?!.,;:''\"]", "", text).split()
        proper_nouns: list[str] = []
        current_group: list[str] = []

        for word in words:
            if word and word[0].isupper() and word.lower() not in _SKIP_WORDS:
                current_group.append(word)
            elif current_group:
                proper_nouns.append(" ".join(current_group))
                current_group = []
        if current_group:
            proper_nouns.append(" ".join(current_group))
        return proper_nouns

    def _select_from_output(self, raw_output: str, valid_id_map: dict[str, Any]) -> Any | None:
        """Estrae dall'output dell'LLM l'id scelto, provando JSON, regex e ricerca diretta."""
        try:
            data = json.loads(self.llm_client.clean_code_block(raw_output))
            if isinstance(data, dict) and data.get("selected_id") in valid_id_map:
                return valid_id_map[data["selected_id"]]
        except Exception:
            pass

        json_match = re.search(r'"selected_id"\s*:\s*"([^"]+)"', raw_output)
        if json_match and json_match.group(1) in valid_id_map:
            return valid_id_map[json_match.group(1)]

        # ultima spiaggia: si cercano gli id dei candidati nel testo grezzo, non un pattern
        # di formato, così la logica resta valida per qualunque KG. Se il modello ne nomina
        # più d'uno la scelta non è deducibile: la posizione nel testo non è una decisione, e
        # un output che ragiona cita per ultimo proprio il candidato che ha scartato.
        mentioned = [
            cand_id
            for cand_id in valid_id_map
            if re.search(rf"(?<!\w){re.escape(cand_id)}(?!\w)", raw_output)
        ]
        return valid_id_map[mentioned[0]] if len(mentioned) == 1 else None

    def _disambiguate_candidates(
        self, question: str, mention: str, candidates: list[EntityCandidate]
    ) -> Any | None:
        """Sceglie il candidato più adatto al contesto della domanda."""
        # la validità dei candidati la decide il connector, così il linker resta agnostico
        valid_cands = [
            c for c in candidates if getattr(c, "id", "") and self.connector.is_valid_candidate(c)
        ]
        if not valid_cands:
            return None
        if len(valid_cands) == 1:
            return valid_cands[0]

        cands_json = [
            {"id": c.id, "label": getattr(c, "label", ""), "description": getattr(c, "description", "")}
            for c in valid_cands
        ]
        try:
            system_prompt = self.llm_client.load_prompt(
                "disambiguate_entity.txt",
                question=question,
                mention=mention,
                candidates_json=json.dumps(cands_json, indent=2, ensure_ascii=False),
            )
            raw_output = self.llm_client.chat(
                system_prompt=system_prompt, user_content=question, temperature=0.0
            )
            selected = self._select_from_output(raw_output, {c.id: c for c in valid_cands})
            if selected is not None:
                return selected
        except Exception as err:
            logger.warning("disambiguazione llm fallita per '%s': %s", mention, err)

        # il primo candidato è l'esito migliore del motore di ricerca del KG: è il ripiego
        # giusto sia quando il modello rifiuta esplicitamente sia quando non si capisce cosa
        # abbia scelto. Registrarlo permette di misurare quanto spesso accade.
        logger.info("disambiguazione non conclusiva per '%s': uso il primo candidato", mention)
        return valid_cands[0]

    def link(self, text: str) -> list[LinkedEntity]:
        """Estrae le menzioni dal testo e le associa agli id del knowledge graph."""
        linked_entities: list[LinkedEntity] = []
        seen_ids: set[str] = set()

        for mention in self._extract_mentions(text):
            mention = self._normalize_mention(mention)
            candidates = self.connector.search_entity(mention, limit=15)
            best_cand = self._disambiguate_candidates(text, mention, candidates)

            if best_cand and best_cand.id not in seen_ids:
                seen_ids.add(best_cand.id)
                linked_entities.append(
                    LinkedEntity(
                        mention=mention,
                        id=best_cand.id,
                        label=best_cand.label or mention,
                        description=getattr(best_cand, "description", "") or "",
                    )
                )
        return linked_entities
