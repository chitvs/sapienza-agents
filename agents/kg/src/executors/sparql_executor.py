import requests
from executors.base_executor import BaseExecutor

class SPARQLExecutionError(Exception):
    """eccezione custom sollevata quando l'esecuzione di una query sparql fallisce."""

    def __init__(self, message: str, query: str):
        super().__init__(message)
        self.query = query

class SPARQLExecutor(BaseExecutor):
    """esecutore di query sparql su endpoint esterni."""

    def __init__(self, endpoint: str = "https://query.wikidata.org/sparql", timeout: float = 15.0):
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "sapienza-agents-bot/1.0 (https://github.com/sapienza-agents; contact@example.com)",
            "Accept": "application/sparql-results+json",
        })

    def execute(self, query: str) -> list[dict]:
        """esegue la query sparql e restituisce i risultati grezzi."""
        try:
            response = self.session.get(
                self.endpoint,
                params={"query": query, "format": "json"},
                timeout=self.timeout
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            raise SPARQLExecutionError("HTTP Error", query=query) from e
        except requests.Timeout as e:
            raise SPARQLExecutionError("timeout superato durante l'esecuzione della query", query=query) from e
        except requests.RequestException as e:
            raise SPARQLExecutionError(f"errore di connessione: {str(e)}", query=query) from e

        data = response.json()
        return data.get("results", {}).get("bindings", [])
