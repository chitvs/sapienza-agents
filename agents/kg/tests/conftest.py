"""Sonda di Ollama e helper di asserzione condivisi da tutta la suite.

La sonda è memorizzata: era ridefinita in dodici file e ognuna faceva una chiamata di rete
al momento della collection, quindi anche `pytest tests/cache` pagava l'attesa di moduli
che non avrebbe eseguito.
"""
from functools import lru_cache

import requests

@lru_cache(maxsize=1)
def is_ollama_running() -> bool:
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def contiene_risposta(result, atteso: str) -> bool:
    """Cerca il testo fra i soli valori di risposta, ignorando le chiavi con underscore.

    Asserire su `str(row)` è ingannevole: la riga contiene anche l'URI in `_sources` e il
    timestamp in `_provenance`, quindi la sottostringa si trova anche a logica rotta.
    """
    valori = (v for row in result.results for k, v in row.items() if not str(k).startswith("_"))
    return any(atteso.lower() in str(v).lower() for v in valori)
