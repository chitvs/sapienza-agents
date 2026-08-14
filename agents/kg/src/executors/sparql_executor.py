import re
from typing import Any

import requests

from executors.base_executor import BaseExecutor, QueryExecutionError
from utils.query_text import mask_literals

_TRANSIENT_STATUS = {429, 502, 503, 504}

class SPARQLExecutionError(QueryExecutionError):
    """Errore durante la validazione o l'esecuzione di una query SPARQL."""

class SPARQLExecutor(BaseExecutor):
    """Esegue query SPARQL su un endpoint remoto, rifiutando tutto ciò che non sia sola lettura."""

    _UPDATE_CLAUSES = (
        (r"INSERT\b", "INSERT"), (r"DELETE\b", "DELETE"), (r"DROP\b", "DROP"),
        (r"CLEAR\b", "CLEAR"), (r"LOAD\b", "LOAD"), (r"CREATE\s+(?:SILENT\s+)?GRAPH\b", "CREATE GRAPH"),
        (r"COPY\b", "COPY"), (r"MOVE\b", "MOVE"), (r"ADD\b", "ADD"),
    )

    def __init__(self, endpoint: str, timeout: float) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
            "Accept": "application/sparql-results+json",
        })

    @classmethod
    def assert_read_only(cls, query: str) -> None:
        """Solleva SPARQLExecutionError se la query contiene una forma di SPARQL Update."""
        # oltre ai letterali si neutralizzano gli IRI: una risorsa come
        # <http://dbpedia.org/resource/Move> non è la clausola MOVE
        without_literals = re.sub(r"<[^>\s]*>", "<>", mask_literals(query))

        for pattern, clause in cls._UPDATE_CLAUSES:
            if re.search(rf"(?<![.:?$\w-]){pattern}", without_literals, flags=re.IGNORECASE):
                raise SPARQLExecutionError(
                    f"SYNTAX_ERROR: la query contiene la clausola di scrittura '{clause}', "
                    f"ma questo agente può solo leggere dal grafo. Riscrivere la query "
                    f"come SELECT o ASK.",
                    query=query,
                )

    def execute(self, query: str) -> list[dict[str, Any]]:
        """Esegue la query e restituisce i binding grezzi."""
        if not re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", query, flags=re.IGNORECASE):
            raise SPARQLExecutionError(
                f"SYNTAX_ERROR: la query non contiene keyword SPARQL valide, "
                f"probabile risposta conversazionale dell'LLM: {query[:100]}",
                query=query,
            )
        self.assert_read_only(query)

        try:
            response = self.session.post(
                self.endpoint,
                data={"query": query, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except ValueError as err:
            raise SPARQLExecutionError(
                f"risposta non interpretabile come JSON: {response.text[:200]}", query=query, retryable=True
            ) from err
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

        # le query ASK restituiscono un booleano invece dei binding
        if "boolean" in data:
            return [{"boolean": data["boolean"]}]
        return data.get("results", {}).get("bindings", [])
