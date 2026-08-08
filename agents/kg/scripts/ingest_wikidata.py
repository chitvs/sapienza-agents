"""
Costruisce gli indici FAISS dell'ontologia Wikidata (proprietà e classi) per il VectorPruner.

Uso: python scripts/ingest_wikidata.py
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

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "wikidata_ontology"

BATCH_SIZE = 50

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
    "Accept": "application/json",
})

def fetch_all_properties() -> list[dict]:
    """Scarica le proprietà Wikidata, escludendo gli identificatori esterni."""
    logger.info("scarico le proprietà Wikidata...")
    query = """
    SELECT ?property ?propertyLabel ?propertyDescription ?propertyType WHERE {
      ?property a wikibase:Property .
      OPTIONAL { ?property wikibase:propertyType ?propertyType . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    """
    response = SESSION.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=120,
    )
    response.raise_for_status()

    properties = []
    identifiers = 0
    for item in response.json().get("results", {}).get("bindings", []):
        prop_uri = item.get("property", {}).get("value", "")
        pid = prop_uri.rsplit("/", 1)[-1]
        if not pid.startswith("P"):
            continue

        prop_type = item.get("propertyType", {}).get("value", "")
        datatype = prop_type.rsplit("#", 1)[-1]

        # gli identificatori esterni non servono a costruire query
        if datatype == "ExternalId":
            identifiers += 1
            continue

        properties.append({
            "id": pid,
            "label": item.get("propertyLabel", {}).get("value", pid),
            "description": item.get("propertyDescription", {}).get("value", ""),
            "datatype": datatype,
        })

    logger.info("trovate %d proprietà semantiche (%d identificatori esclusi)", len(properties), identifiers)
    return properties

def fetch_common_classes(top_n: int = 500) -> list[dict]:
    """Scarica le N classi più usate come valore di P31, con etichetta e descrizione."""
    logger.info("scarico le %d classi Wikidata più usate...", top_n)
    query = f"""
    SELECT ?class (COUNT(?item) AS ?count) WHERE {{
      ?item wdt:P31 ?class .
    }} GROUP BY ?class ORDER BY DESC(?count) LIMIT {top_n}
    """
    response = SESSION.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=120,
    )
    response.raise_for_status()

    class_ids = []
    for row in response.json().get("results", {}).get("bindings", []):
        qid = row.get("class", {}).get("value", "").rsplit("/", 1)[-1]
        if qid.startswith("Q"):
            class_ids.append(qid)

    # le etichette si risolvono a parte: unendo SERVICE wikibase:label alla query di
    # aggregazione il join avverrebbe prima del raggruppamento e andrebbe in timeout
    logger.info("risolvo etichette e descrizioni di %d classi...", len(class_ids))
    classes = []
    for start in range(0, len(class_ids), BATCH_SIZE):
        batch = class_ids[start:start + BATCH_SIZE]
        resp = SESSION.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|descriptions",
                "languages": "en",
                "format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        entities = resp.json().get("entities", {})
        for qid in batch:
            data = entities.get(qid, {})
            classes.append({
                "id": qid,
                "label": data.get("labels", {}).get("en", {}).get("value", qid),
                "description": data.get("descriptions", {}).get("en", {}).get("value", ""),
            })
        time.sleep(0.15)

    logger.info("risolte %d classi", len(classes))
    return classes

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

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # il modello va letto da src: l'indice deve nascere nello stesso spazio vettoriale
    # in cui il VectorPruner incorpora le domande a runtime
    from embeddings import RETRIEVAL_MODEL_NAME

    logger.info("carico il modello di embedding (%s)...", RETRIEVAL_MODEL_NAME)
    model = SentenceTransformer(RETRIEVAL_MODEL_NAME)

    properties = fetch_all_properties()
    classes = fetch_common_classes()

    # si incorporano i testi del corpus, quindi senza il prefisso di istruzione che
    # bge richiede solo lato query
    logger.info("genero gli embedding per %d proprietà...", len(properties))
    prop_emb = model.encode(
        [build_embedding_text(p) for p in properties], show_progress_bar=True, convert_to_numpy=True
    )
    logger.info("genero gli embedding per %d classi...", len(classes))
    class_emb = model.encode(
        [build_embedding_text(c) for c in classes], show_progress_bar=True, convert_to_numpy=True
    )

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
