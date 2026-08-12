"""Costruzione dell'indice FAISS dell'ontologia, condivisa dai due script di ingest."""

import json
import logging
import sys
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

def build_embedding_text(item: dict) -> str:
    """Compone il testo da incorporare per una proprietà o una classe."""
    label = item.get("label", "") or item.get("id", "")
    description = item.get("description", "")
    return f"{label} - {description}" if description else label

def create_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Crea un indice FAISS per la ricerca per similarità coseno."""
    # la normalizzazione rende il prodotto interno equivalente alla similarità coseno
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index

def build_and_save(properties: list[dict], classes: list[dict], output_dir: Path) -> None:
    """Incorpora proprietà e classi e scrive indici e metadati, allineati per posizione."""
    # la guardia sta qui e non nei due chiamanti: un insieme vuoto farebbe costruire
    # l'indice da una matrice priva di dimensioni, con un IndexError che arriverebbe a
    # scaricamento ed embedding già pagati
    if not properties or not classes:
        mancante = "proprietà" if not properties else "classi"
        sys.exit(f"nessuna {mancante} scaricata: l'endpoint potrebbe essere non disponibile, riprova più tardi.")

    # il modello va letto da src: l'indice deve nascere nello stesso spazio vettoriale in
    # cui il VectorPruner incorpora le domande a runtime
    from embeddings import RETRIEVAL_MODEL_NAME

    logger.info("carico il modello di embedding (%s)...", RETRIEVAL_MODEL_NAME)
    model = SentenceTransformer(RETRIEVAL_MODEL_NAME)

    output_dir.mkdir(parents=True, exist_ok=True)
    for nome, items in (("properties", properties), ("classes", classes)):
        logger.info("genero gli embedding per %d %s...", len(items), nome)
        # si incorporano i testi del corpus, quindi senza il prefisso di istruzione che
        # bge richiede solo lato query
        emb = model.encode(
            [build_embedding_text(i) for i in items], show_progress_bar=True, convert_to_numpy=True
        )
        faiss.write_index(create_faiss_index(emb.astype(np.float32)), str(output_dir / f"{nome}.faiss"))
        meta = [{"index": i, **item} for i, item in enumerate(items)]
        (output_dir / f"{nome}_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("  %s.faiss: %d voci", nome, len(items))

    logger.info("fatto. file salvati in %s", output_dir)
