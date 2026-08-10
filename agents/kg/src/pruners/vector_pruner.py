import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import faiss

from embeddings import BGE_QUERY_INSTRUCTION, RETRIEVAL_MODEL_NAME, get_embedding_model
from pruners.base_pruner import BasePruner, PrunedSchema

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wikidata_ontology"

# Con bge-small-en-v1.5 le proprietà corrette per domande indirette (es. "author",
# "place of birth") cadono nel top-15 ma non nel top-10 del ranking semantico.
_MAX_SUGGESTED_PROPS = 15

class VectorPruner(BasePruner):
    """Seleziona lo schema rilevante cercando proprietà e classi in un indice FAISS."""

    def __init__(
        self,
        index_dir: str | Path | None = None,
        ingest_script: str = "scripts/ingest_wikidata.py",
    ) -> None:
        index_path = Path(index_dir) if index_dir else _DEFAULT_INDEX_DIR
        self.ingest_script = ingest_script

        prop_index_file = index_path / "properties.faiss"
        class_index_file = index_path / "classes.faiss"
        prop_meta_file = index_path / "properties_meta.json"
        class_meta_file = index_path / "classes_meta.json"

        if not prop_index_file.exists():
            raise FileNotFoundError(
                f"Indice FAISS delle proprietà non trovato in {prop_index_file}. "
                f"È un artefatto di build da generare una volta per macchina "
                f"con 'python {ingest_script}' dalla directory agents/kg."
            )

        self.prop_index = faiss.read_index(str(prop_index_file))
        self.prop_meta: list[dict] = json.loads(prop_meta_file.read_text(encoding="utf-8"))

        if class_index_file.exists():
            self.class_index = faiss.read_index(str(class_index_file))
            self.class_meta: list[dict] = json.loads(class_meta_file.read_text(encoding="utf-8"))
        else:
            self.class_index = None
            self.class_meta = []

        logger.info("VectorPruner pronto (il modello viene caricato al primo uso).")

    def _search(self, index: Any, meta: list[dict], question: str, top_k: int) -> list[dict]:
        """Cerca i termini più affini alla domanda nell'indice indicato."""
        if index is None:
            return []
        model = get_embedding_model(RETRIEVAL_MODEL_NAME)
        # bge richiede il prefisso di istruzione solo lato query, non sul corpus
        q_vec = model.encode([BGE_QUERY_INSTRUCTION + question], convert_to_numpy=True).astype(np.float32)
        faiss.normalize_L2(q_vec)

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

    def _search_properties(self, question: str, top_k: int = 15) -> list[dict]:
        """Cerca le proprietà semanticamente più rilevanti nell'ontologia del KG."""
        return self._search(self.prop_index, self.prop_meta, question, top_k)

    def _search_classes(self, question: str, top_k: int = 5) -> list[dict]:
        """Cerca le classi semanticamente più rilevanti nell'ontologia del KG."""
        return self._search(self.class_index, self.class_meta, question, top_k)

    @staticmethod
    def _describe(item: dict, prefix: str) -> str:
        """Formatta un termine dell'ontologia per il contesto dell'LLM."""
        desc = item.get("description", "")
        return f"  {prefix}{item['id']} - {item['label']}" + (f" ({desc})" if desc else "")

    def prune(
        self,
        seed_entity_ids: list[str],
        connector: Any = None,
        max_items: int = 20,
        question: str = "",
    ) -> PrunedSchema:
        """Costruisce il contesto unendo entità seed, proprietà verificate e match semantici."""
        context_lines: list[str] = []
        entity_prefix, property_prefix = self._prefixes(connector)

        def entity_ref(eid: str) -> str:
            if connector is not None:
                return connector.format_entity_ref(eid)
            return f"{entity_prefix}{eid}"

        # proprietà realmente presenti sulle entità seed, per distinguere verificate da suggerite
        existing_pids: set[str] = set()

        if seed_entity_ids and connector:
            entities_dict = connector.get_entities(seed_entity_ids)

            for eid in seed_entity_ids:
                entity_data = entities_dict.get(eid)
                if not (entity_data and getattr(entity_data, "id", None)):
                    context_lines.append(f"entity: {entity_ref(eid)}")
                    continue

                desc = getattr(entity_data, "description", "") or ""
                desc_str = f" - {desc}" if desc else ""
                context_lines.append(f"entity: {entity_ref(entity_data.id)} ({entity_data.label}{desc_str})")
                if desc:
                    context_lines.append(f'description: "{desc}"')

                # l'identificatore è il primo token della chiave: vale sia per Wikidata
                # ("P569 (date of birth)") sia per vocabolari con nomi ("birthPlace")
                for prop_key in getattr(entity_data, "properties", {}):
                    token = prop_key.split(" ", 1)[0].strip()
                    if token:
                        existing_pids.add(token)
        elif seed_entity_ids:
            context_lines.extend(f"entity: {entity_ref(eid)}" for eid in seed_entity_ids)

        if question:
            relevant_props = self._search_properties(question, top_k=max_items)
            if relevant_props:
                verified = [p for p in relevant_props if p["id"] in existing_pids]
                suggested = [p for p in relevant_props if p["id"] not in existing_pids]

                context_lines.append("")
                if verified:
                    context_lines.append("VERIFIED properties (exist as outbound edges on the seed entities):")
                    context_lines.extend(self._describe(p, property_prefix) for p in verified)
                if suggested:
                    context_lines.append("")
                    context_lines.append("SUGGESTED properties (semantic match, useful for inverse edges or target types):")
                    context_lines.extend(
                        self._describe(p, property_prefix) for p in suggested[:_MAX_SUGGESTED_PROPS]
                    )

            relevant_classes = self._search_classes(question, top_k=5)
            if relevant_classes:
                context_lines.append("")
                context_lines.append("relevant classes for this question:")
                context_lines.extend(self._describe(c, entity_prefix) for c in relevant_classes)

        if not context_lines:
            context_lines.extend(f"entity: {entity_ref(seed_id)}" for seed_id in seed_entity_ids)

        return PrunedSchema(context_text="\n".join(context_lines))
