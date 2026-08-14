"""Sonde dei servizi esterni e helper di asserzione condivisi da tutta la suite.

Le sonde sono memorizzate: erano ridefinite in una dozzina di file e ognuna faceva una
chiamata di rete al momento della collection, quindi anche `pytest tests/cache` pagava
l'attesa di servizi che non avrebbe interrogato.
"""
from functools import lru_cache

import requests

@lru_cache(maxsize=1)
def is_ollama_running() -> bool:
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@lru_cache(maxsize=1)
def is_wikidata_reachable() -> bool:
    try:
        return requests.head("https://www.wikidata.org/w/api.php", timeout=3).status_code < 500
    except Exception:
        return False

@lru_cache(maxsize=1)
def is_wikidata_endpoint_reachable() -> bool:
    """L'endpoint SPARQL è un servizio distinto dalle API di ricerca, e cade per conto suo."""
    try:
        return requests.head("https://query.wikidata.org/sparql", timeout=3).status_code < 500
    except Exception:
        return False

@lru_cache(maxsize=1)
def is_dbpedia_reachable() -> bool:
    try:
        return requests.get("https://dbpedia.org/sparql", timeout=5).status_code < 500
    except Exception:
        return False

@lru_cache(maxsize=1)
def is_neo4j_ready() -> bool:
    """Verifica che Neo4j risponda e che il movie graph sia effettivamente caricato."""
    try:
        from configs.settings import settings
        from executors.cypher_executor import CypherExecutor

        executor = CypherExecutor(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            timeout=5.0,
        )
        rows = executor.execute_trusted("MATCH (m:Movie) RETURN count(m) AS c", {})
        executor.close()
        return bool(rows) and rows[0].get("c", 0) > 0
    except Exception:
        return False

def contains_answer(result, expected: str) -> bool:
    """Cerca il testo fra i soli valori di risposta, ignorando le chiavi con underscore.

    Asserire su `str(row)` è ingannevole: la riga contiene anche l'URI in `_sources` e il
    timestamp in `_provenance`, quindi la sottostringa si trova anche a logica rotta.
    """
    values = (v for row in result.results for k, v in row.items() if not str(k).startswith("_"))
    return any(expected.lower() in str(v).lower() for v in values)
