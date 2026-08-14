"""
Costruisce gli indici FAISS dell'ontologia Wikidata (proprietà e classi) per il VectorPruner.

Uso: python scripts/ingest_wikidata.py
"""

import logging
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ontology_index import build_and_save  # noqa: E402

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

def main() -> None:
    properties = fetch_all_properties()
    classes = fetch_common_classes()
    build_and_save(properties, classes, OUTPUT_DIR)

if __name__ == "__main__":
    main()
