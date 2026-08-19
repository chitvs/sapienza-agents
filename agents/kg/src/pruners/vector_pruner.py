import json
import logging
from pathlib import Path
from typing import Any
import numpy as np
import faiss
from connectors.base_connector import BaseConnector, KnowledgeGraphUnavailableError
from models.embeddings import BGE_QUERY_INSTRUCTION, RETRIEVAL_MODEL_NAME, get_embedding_model
from configs.settings import settings
from pruners.base_pruner import BasePruner, PrunedSchema

# configurazione logger
logger = logging.getLogger(__name__)

# variabili globali
_DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wikidata_ontology"

# le classi servono solo a suggerire il tipo del soggetto: oltre le prime aggiungono rumore
_CLASS_RESULTS = 5

class VectorPruner(BasePruner):
    """Seleziona lo schema rilevante cercando proprietà e classi in un indice FAISS."""

    def __init__(
        self,
        connector: BaseConnector,
        index_dir: str | Path | None = None,
        ingest_script: str = "scripts/ingest_wikidata.py",
    ) -> None:
        super().__init__(connector)
        index_path = Path(index_dir) if index_dir else _DEFAULT_INDEX_DIR

        prop_index_file = index_path / "properties.faiss"
        class_index_file = index_path / "classes.faiss"

        if not prop_index_file.exists():
            raise FileNotFoundError(
                f"Indice FAISS delle proprietà non trovato in {prop_index_file}. "
                f"È un artefatto di build da generare una volta per macchina "
                f"con 'python {ingest_script}' dalla directory agents/kg."
            )

        self.prop_index = faiss.read_index(str(prop_index_file))
        self.prop_meta: list[dict] = json.loads(
            (index_path / "properties_meta.json").read_text(encoding="utf-8")
        )

        if class_index_file.exists():
            self.class_index = faiss.read_index(str(class_index_file))
            self.class_meta: list[dict] = json.loads(
                (index_path / "classes_meta.json").read_text(encoding="utf-8")
            )
        else:
            self.class_index = None
            self.class_meta = []

        logger.info("VectorPruner pronto (il modello viene caricato al primo uso).")

    @staticmethod
    def _embed_question(question: str) -> Any:
        """Incorpora la domanda per la ricerca vettoriale."""
        model = get_embedding_model(RETRIEVAL_MODEL_NAME)
        # bge richiede il prefisso di istruzione solo lato query, non sul corpus
        q_vec = model.encode([BGE_QUERY_INSTRUCTION + question], convert_to_numpy=True).astype(np.float32)
        faiss.normalize_L2(q_vec)
        return q_vec

    def _search(self, index: Any, meta: list[dict], q_vec: Any, top_k: int) -> list[dict]:
        """Cerca i termini più affini alla domanda già incorporata nell'indice indicato."""
        if index is None:
            return []
        scores, indices = index.search(q_vec, top_k)
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(meta):
                continue
            results.append({
                "id": meta[idx]["id"],
                "label": meta[idx]["label"],
                "description": meta[idx].get("description", ""),
                "score": float(scores[0][i]),
            })
        return results

    @staticmethod
    def _describe(item: dict, prefix: str) -> str:
        """Formatta un termine dell'ontologia per il contesto dell'LLM."""
        desc = item.get("description", "")
        return f"  {prefix}{item['id']} - {item['label']}" + (f" ({desc})" if desc else "")

    def _seed_context(self, seed_entity_ids: list[str], context_lines: list[str]) -> set[str]:
        """Descrive le entità seed e restituisce le proprietà che possiedono davvero."""
        try:
            entities_dict = self.connector.get_entities(seed_entity_ids)
        except KnowledgeGraphUnavailableError:
            raise
        except Exception as err:
            logger.warning("entità seed non leggibili dal KG: %s", err)
            entities_dict = {}

        existing_pids: set[str] = set()
        for eid in seed_entity_ids:
            entity_data = entities_dict.get(eid)
            if entity_data is None:
                context_lines.append(f"entity: {self.connector.format_entity_ref(eid)}")
                continue

            desc = entity_data.description or ""
            desc_str = f" - {desc}" if desc else ""
            context_lines.append(
                f"entity: {self.connector.format_entity_ref(entity_data.id)} ({entity_data.label}{desc_str})"
            )
            if desc:
                context_lines.append(f'description: "{desc}"')

            # l'identificatore è il primo token della chiave: vale sia per Wikidata
            # ("P569 (date of birth)") sia per vocabolari con nomi ("birthPlace")
            for prop_key in entity_data.properties:
                token = prop_key.split(" ", 1)[0].strip()
                if token:
                    existing_pids.add(token)
        return existing_pids

    def prune(self, seed_entity_ids: list[str], question: str = "") -> PrunedSchema:
        """Costruisce il contesto unendo entità seed, proprietà verificate e match semantici."""
        context_lines: list[str] = []
        # le proprietà già presenti sulle entità seed distinguono le verificate dalle suggerite
        existing_pids = self._seed_context(seed_entity_ids, context_lines) if seed_entity_ids else set()

        if question:
            q_vec = self._embed_question(question)
            relevant_props = self._search(
                self.prop_index, self.prop_meta, q_vec, settings.schema_search_pool
            )
            if relevant_props:
                verified = [p for p in relevant_props if p["id"] in existing_pids]
                suggested = [p for p in relevant_props if p["id"] not in existing_pids]
                prefix = self.connector.property_prefix

                context_lines.append("")
                if verified:
                    context_lines.append("VERIFIED properties (exist as outbound edges on the seed entities):")
                    context_lines.extend(self._describe(p, prefix) for p in verified)
                if suggested:
                    context_lines.append("")
                    context_lines.append("SUGGESTED properties (semantic match, useful for inverse edges or target types):")
                    context_lines.extend(
                        self._describe(p, prefix) for p in suggested[:settings.schema_max_suggested]
                    )

            relevant_classes = self._search(self.class_index, self.class_meta, q_vec, _CLASS_RESULTS)
            if relevant_classes:
                context_lines.append("")
                context_lines.append("relevant classes for this question:")
                context_lines.extend(
                    self._describe(c, self.connector.class_prefix) for c in relevant_classes
                )

        return PrunedSchema(context_text="\n".join(context_lines))
