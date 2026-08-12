import json
import logging
import math
import re
from typing import Any

from connectors.base_connector import BaseConnector, EntityCandidate
from embeddings import BGE_QUERY_INSTRUCTION, RETRIEVAL_MODEL_NAME, get_embedding_model
from linkers.base_linker import BaseLinker, LinkedEntity
from llm import build_llm_client
from mention_extraction import extract_entity_mentions
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

class EntityLinker(BaseLinker):
    """Entity linker zero-shot: GLiNER estrae le menzioni, l'LLM le disambigua e, quando
    non è conclusivo, decide la combinazione di contesto, notorietà e rank di ricerca."""

    def __init__(self, connector: BaseConnector, llm_client: OllamaClient | None = None) -> None:
        self.connector = connector
        self.llm_client = llm_client or build_llm_client(settings.ollama_linking_model)

    def _extract_mentions(self, text: str) -> list[str]:
        """Estrae le menzioni di entità, con fallback progressivi se GLiNER non produce nulla."""
        try:
            candidates = extract_entity_mentions(text)
            if candidates:
                filtered = self._filter_mentions(text, candidates)
                if filtered:
                    return filtered
        except Exception as err:
            logger.warning("estrazione/filtro menzioni gliner fallita: %s", err)

        proper_nouns = self._fallback_extract_proper_nouns(text)
        if proper_nouns:
            return proper_nouns

        clean_text = re.sub(r"[?!.,;:]", "", text).strip()
        return [clean_text] if clean_text else []

    def _filter_mentions(self, question: str, candidates: list[str]) -> list[str]:
        """Scarta dalle menzioni GLiNER i ruoli e gli attributi generici, tenendo le entità nominate."""
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
        # l'apostrofo non è punteggiatura da togliere qui: "McDonald's" e "Shakespeare's"
        # si distinguono solo interrogando il KG, e ci pensa _search_mention
        words = re.sub(r"[?!.,;:\"]", "", text).split()
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
        mentioned: list[str] = []
        remaining = raw_output
        # dal più lungo al più corto, cancellando via via il testo già attribuito: su
        # DBpedia un id può contenerne un altro (Berlin dentro Berlin,_Ohio), e una
        # scelta univoca sembrerebbe ambigua
        for cand_id in sorted(valid_id_map, key=len, reverse=True):
            pattern = rf"(?<!\w){re.escape(cand_id)}(?!\w)"
            if re.search(pattern, remaining):
                mentioned.append(cand_id)
                remaining = re.sub(pattern, " ", remaining)
        return valid_id_map[mentioned[0]] if len(mentioned) == 1 else None

    def _disambiguate_candidates(
        self, question: str, mention: str, candidates: list[EntityCandidate]
    ) -> Any | None:
        """Sceglie il candidato più adatto al contesto della domanda."""
        # la validità dei candidati la decide il connector, così il linker resta agnostico
        valid_cands = [c for c in candidates if c.id and self.connector.is_valid_candidate(c)]
        if not valid_cands:
            return None
        if len(valid_cands) == 1:
            return valid_cands[0]

        cands_json = [
            {"id": c.id, "label": c.label, "description": c.description or ""} for c in valid_cands
        ]
        raw_output = ""
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

        # Si registra la risposta grezza perché dal log non si distingue altrimenti un rifiuto
        # esplicito del modello da un output che il parser non ha saputo interpretare, e le
        # due cose richiedono rimedi opposti.
        fallback = self._rank_candidates(question, valid_cands)
        logger.info(
            "disambiguazione non conclusiva per '%s': ripiego sul candidato meglio classificato (%s). risposta grezza: %r",
            mention,
            fallback.id,
            (raw_output or "")[:200],
        )
        return fallback

    @staticmethod
    def _rescale(values: list[float]) -> list[float]:
        """Riporta i punteggi in [0,1] dentro l'insieme dei candidati, per poterli sommare."""
        low, high = min(values), max(values)
        return [0.5] * len(values) if high == low else [(v - low) / (high - low) for v in values]

    def _context_scores(self, question: str, candidates: list[EntityCandidate]) -> list[float]:
        """Affinità fra la domanda e la descrizione di ciascun candidato."""
        try:
            model = get_embedding_model(RETRIEVAL_MODEL_NAME)
            descriptions = [c.description or "" for c in candidates]
            vectors = model.encode(
                [BGE_QUERY_INSTRUCTION + question] + descriptions,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return self._rescale([
                float(s) if descriptions[i] else 0.0 for i, s in enumerate(vectors[1:] @ vectors[0])
            ])
        except Exception as err:
            logger.warning("affinità semantica dei candidati non calcolabile: %s", err)
            return [0.5] * len(candidates)

    def _prominence_scores(self, candidates: list[EntityCandidate]) -> list[float]:
        """Notorietà di ciascun candidato secondo il KG, in scala logaritmica."""
        prominence = self.connector.candidate_prominence(candidates)
        if not prominence:
            return [0.5] * len(candidates)
        # fra 2 e 20 sitelink la differenza di notorietà è reale, fra 200 e 220 è rumore
        return self._rescale([math.log1p(prominence.get(c.id, 0.0)) for c in candidates])

    def _rank_candidates(self, question: str, candidates: list[EntityCandidate]) -> EntityCandidate:
        """Sceglie un candidato combinando notorietà, posizione nella ricerca e affinità col contesto."""
        if len(candidates) == 1:
            return candidates[0]

        context = self._context_scores(question, candidates)
        prominence = self._prominence_scores(candidates)
        search_rank = self._rescale([1.0 / math.log2(i + 2) for i in range(len(candidates))])

        scores = [(c + p + r) / 3 for c, p, r in zip(context, prominence, search_rank)]
        return candidates[max(range(len(candidates)), key=lambda i: scores[i])]

    def _search_mention(self, mention: str) -> tuple[str, list[EntityCandidate]]:
        """Cerca la menzione com'è, e solo se il KG non conosce nulla riprova senza il possessivo."""
        # "McDonald's" e "Levi's" sono nomi propri, non genitivi: togliere il suffisso a
        # priori li trasformerebbe in un'altra entità, quasi sempre una persona
        candidates = self.connector.search_entity(mention, limit=settings.linker_candidates)
        if candidates:
            return mention, candidates

        stripped = self._normalize_mention(mention)
        if stripped and stripped != mention:
            return stripped, self.connector.search_entity(stripped, limit=settings.linker_candidates)
        return mention, candidates

    def link(self, text: str) -> list[LinkedEntity]:
        """Estrae le menzioni dal testo e le associa agli id del knowledge graph."""
        linked_entities: list[LinkedEntity] = []
        seen_ids: set[str] = set()

        for raw_mention in self._extract_mentions(text):
            mention, candidates = self._search_mention(raw_mention.strip())
            best_cand = self._disambiguate_candidates(text, mention, candidates)

            if best_cand and best_cand.id not in seen_ids:
                seen_ids.add(best_cand.id)
                linked_entities.append(
                    LinkedEntity(
                        mention=mention,
                        id=best_cand.id,
                        label=best_cand.label or mention,
                        description=best_cand.description or "",
                    )
                )
        return linked_entities
