import re
from typing import Any

import requests

from executors.base_executor import BaseExecutor, QueryExecutionError

_TRANSIENT_STATUS = {429, 502, 503, 504}

class SPARQLExecutionError(QueryExecutionError):
    """Errore durante la validazione o l'esecuzione di una query SPARQL."""

class SPARQLExecutor(BaseExecutor):
    """Esegue query SPARQL su un endpoint remoto."""

    def __init__(
        self,
        endpoint: str = "https://query.wikidata.org/sparql",
        timeout: float = 15.0,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
            "Accept": "application/sparql-results+json",
        })

    def execute(self, query: str) -> list[dict[str, Any]]:
        """Esegue la query e restituisce i binding grezzi."""
        if not re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", query, flags=re.IGNORECASE):
            raise SPARQLExecutionError(
                f"SYNTAX_ERROR: la query non contiene keyword SPARQL valide, "
                f"probabile risposta conversazionale dell'LLM: {query[:100]}",
                query=query,
            )

        try:
            response = self.session.post(
                self.endpoint,
                data={"query": query, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            detail = f"HTTP {status}" if status else "HTTP Error"
            if err.response is not None:
                detail += f": {err.response.text[:500]}"
            raise SPARQLExecutionError(detail, query=query, retryable=status in _TRANSIENT_STATUS) from err
        except requests.Timeout as err:
            raise SPARQLExecutionError(
                "timeout superato durante l'esecuzione della query", query=query, retryable=True
            ) from err
        except requests.RequestException as err:
            raise SPARQLExecutionError(f"errore di connessione: {err}", query=query, retryable=True) from err

        data = response.json()
        # le query ASK restituiscono un booleano invece dei binding
        if "boolean" in data:
            return [{"boolean": data["boolean"]}]
        return data.get("results", {}).get("bindings", [])
