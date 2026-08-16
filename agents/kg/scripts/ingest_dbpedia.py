"""
Costruisce gli indici FAISS dell'ontologia DBpedia (vocabolario dbo:) per il VectorPruner.

Uso: python scripts/ingest_dbpedia.py
"""

import logging
import sys
import time
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ontology_index import build_and_save

# configurazione logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# variabili globali
DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
DBPEDIA_ONTOLOGY_NS = "http://dbpedia.org/ontology/"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "dbpedia_ontology"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
    "Accept": "application/sparql-results+json",
})

def run_sparql(query: str, retries: int = 3) -> list[dict]:
    """Esegue una query sull'endpoint pubblico e ne restituisce le righe dei risultati JSON."""
    for attempt in range(retries):
        try:
            response = SESSION.get(
                DBPEDIA_SPARQL,
                params={"query": query, "format": "application/sparql-results+json"},
                timeout=120,
            )
            # 429 e 503 sono codici di endpoint occupato
            # aspettiamo e ritentiamo
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
    """Trasforma un URI nel suo nome locale."""
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

def main() -> None:
    properties = fetch_ontology_terms("property")
    classes = fetch_ontology_terms("class")
    build_and_save(properties, classes, OUTPUT_DIR)

if __name__ == "__main__":
    main()
