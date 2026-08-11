"""
Costruisce gli indici FAISS dell'ontologia DBpedia (vocabolario dbo:) per il VectorPruner.

Uso: python scripts/ingest_dbpedia.py
"""

import json
import logging
import sys
import time
from pathlib import Path

import faiss
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
DBPEDIA_ONTOLOGY_NS = "http://dbpedia.org/ontology/"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "dbpedia_ontology"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
    "Accept": "application/sparql-results+json",
})

def run_sparql(query: str, retries: int = 3) -> list[dict]:
    """Esegue una query sull'endpoint pubblico."""
    for attempt in range(retries):
        try:
            response = SESSION.get(
                DBPEDIA_SPARQL,
                params={"query": query, "format": "application/sparql-results+json"},
                timeout=120,
            )
            if response.status_code in (429, 503):
                wait = 3.0 * (attempt + 1)
                logger.warning("endpoint occupato (%s), attendo %.0fs...", response.status_code, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json().get("results", {}).get("bindings", [])
        except Exception as err:
            if attempt == retries - 1:
                raise
            logger.warning("tentativo %d fallito (%s), ritento...", attempt + 1, err)
            time.sleep(3.0 * (attempt + 1))
    return []

def local_name(uri: str) -> str:
    return uri[len(DBPEDIA_ONTOLOGY_NS):] if uri.startswith(DBPEDIA_ONTOLOGY_NS) else uri.rsplit("/", 1)[-1]

def fetch_ontology_terms(term_type: str) -> list[dict]:
    """
    Scarica le proprietà (owl:ObjectProperty / owl:DatatypeProperty) o le classi
    (owl:Class) dell'ontologia dbo:, con etichetta e commento in inglese.
    """
    if term_type == "property":
        type_filter = "?term a ?t . FILTER(?t IN (owl:ObjectProperty, owl:DatatypeProperty))"
    else:
        type_filter = "?term a owl:Class ."

    query = f"""
    SELECT DISTINCT ?term ?label ?comment WHERE {{
      {type_filter}
      FILTER(STRSTARTS(STR(?term), "{DBPEDIA_ONTOLOGY_NS}"))
      OPTIONAL {{ ?term rdfs:label ?label . FILTER(lang(?label) = "en") }}
      OPTIONAL {{ ?term rdfs:comment ?comment . FILTER(lang(?comment) = "en") }}
    }}
    """
    logger.info("scarico le %s dell'ontologia dbo:...", "proprietà" if term_type == "property" else "classi")
    rows = run_sparql(query)

    terms: dict[str, dict] = {}
    for row in rows:
        uri = row.get("term", {}).get("value", "")
        if not uri.startswith(DBPEDIA_ONTOLOGY_NS):
            continue
        name = local_name(uri)
        if name in terms:
            continue
        terms[name] = {
            "id": name,
            "label": row.get("label", {}).get("value", "") or name,
            "description": row.get("comment", {}).get("value", "")[:300],
        }

    logger.info("trovate %d %s", len(terms), "proprietà" if term_type == "property" else "classi")
    return list(terms.values())

def build_embedding_text(item: dict) -> str:
    text = item.get("label", "") or item.get("id", "")
    description = item.get("description", "")
    return f"{text} - {description}" if description else text

def create_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from embeddings import RETRIEVAL_MODEL_NAME

    logger.info("carico il modello di embedding (%s)...", RETRIEVAL_MODEL_NAME)
    model = SentenceTransformer(RETRIEVAL_MODEL_NAME)

    properties = fetch_ontology_terms("property")
    classes = fetch_ontology_terms("class")

    if not properties:
        sys.exit("nessuna proprietà scaricata: l'endpoint DBpedia potrebbe essere non disponibile, riprova più tardi.")

    logger.info("genero gli embedding per %d proprietà...", len(properties))
    prop_emb = model.encode([build_embedding_text(p) for p in properties], show_progress_bar=True, convert_to_numpy=True)

    logger.info("genero gli embedding per %d classi...", len(classes))
    class_emb = model.encode([build_embedding_text(c) for c in classes], show_progress_bar=True, convert_to_numpy=True)

    faiss.write_index(create_faiss_index(prop_emb.astype(np.float32)), str(OUTPUT_DIR / "properties.faiss"))
    faiss.write_index(create_faiss_index(class_emb.astype(np.float32)), str(OUTPUT_DIR / "classes.faiss"))

    for filename, items in (("properties_meta.json", properties), ("classes_meta.json", classes)):
        meta = [{"index": i, **item} for i, item in enumerate(items)]
        (OUTPUT_DIR / filename).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("fatto. file salvati in %s", OUTPUT_DIR)
    logger.info("  properties.faiss: %d voci", len(properties))
    logger.info("  classes.faiss: %d voci", len(classes))

if __name__ == "__main__":
    main()
