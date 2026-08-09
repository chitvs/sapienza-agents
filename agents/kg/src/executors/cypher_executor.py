import re
import logging
from typing import Any

from executors.base_executor import BaseExecutor

logger = logging.getLogger(__name__)

class CypherExecutionError(Exception):
    """Errore durante la validazione o l'esecuzione di una query Cypher."""

    def __init__(self, message: str, query: str) -> None:
        super().__init__(message)
        self.query = query

class CypherExecutor(BaseExecutor):
    """Esegue query Cypher su Neo4j, rifiutando tutto ciò che non sia sola lettura."""

    # La query arriva da un LLM: un falso positivo (query di lettura rifiutata) costa
    # molto meno di una scrittura accidentale sul database dell'utente.
    _WRITE_CLAUSES = (
        "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP",
        "LOAD CSV", "FOREACH", "CALL {", "TERMINATE",
    )

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.timeout = timeout
        self._driver: Any = None

    def _get_driver(self) -> Any:
        """Crea il driver al primo uso, così importare il modulo non richiede un DB attivo."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as err:
                raise CypherExecutionError(
                    "driver neo4j non installato: eseguire 'pip install neo4j'", query=""
                ) from err
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                connection_acquisition_timeout=self.timeout,
            )
        return self._driver

    @classmethod
    def assert_read_only(cls, query: str) -> None:
        """Solleva CypherExecutionError se la query contiene clausole di scrittura."""
        # le occorrenze dentro stringhe letterali non contano: un film intitolato
        # "CREATE OR DELETE" non deve far scattare il controllo
        without_literals = re.sub(r"'[^']*'|\"[^\"]*\"", "''", query)
        upper = without_literals.upper()

        for clause in cls._WRITE_CLAUSES:
            pattern = re.escape(clause) if not clause.isalpha() else rf"\b{re.escape(clause)}\b"
            if re.search(pattern, upper):
                raise CypherExecutionError(
                    f"SYNTAX_ERROR: la query contiene la clausola di scrittura '{clause}', "
                    f"ma questo agente può solo leggere dal grafo. Riscrivere la query "
                    f"usando esclusivamente MATCH/OPTIONAL MATCH/WHERE/RETURN.",
                    query=query,
                )

    def _run_with_params(self, query: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Esegue la query in una transazione di sola lettura."""
        try:
            from neo4j.exceptions import Neo4jError, ServiceUnavailable
        except ImportError:
            Neo4jError = ServiceUnavailable = Exception  # type: ignore[assignment, misc]

        driver = self._get_driver()
        session_kwargs = {"database": self.database} if self.database else {}

        try:
            with driver.session(default_access_mode="READ", **session_kwargs) as session:
                # il timeout va sulla transazione: passato a run() diventerebbe un
                # parametro della query anziché un limite di tempo
                with session.begin_transaction(timeout=self.timeout) as tx:
                    return [record.data() for record in tx.run(query, params or {})]
        except ServiceUnavailable as err:
            raise CypherExecutionError(f"neo4j non raggiungibile su {self.uri}: {err}", query=query) from err
        except Neo4jError as err:
            raise CypherExecutionError(str(err), query=query) from err
        except CypherExecutionError:
            raise
        except Exception as err:
            raise CypherExecutionError(f"errore durante l'esecuzione: {err}", query=query) from err

    def run_internal(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Esegue una query di servizio scritta da noi, saltando il controllo anti-allucinazione."""
        self.assert_read_only(query)
        return self._run_with_params(query, params)

    def execute(self, query: str) -> list[dict[str, Any]]:
        """Valida ed esegue in sola lettura la query generata dall'LLM."""
        if not re.search(r"\b(MATCH|RETURN|UNWIND|WITH|CALL)\b", query, flags=re.IGNORECASE):
            raise CypherExecutionError(
                f"SYNTAX_ERROR: la query non contiene keyword Cypher valide, "
                f"probabile risposta conversazionale dell'LLM: {query[:100]}",
                query=query,
            )
        self.assert_read_only(query)
        return self._run_with_params(query, None)

    def close(self) -> None:
        """Chiude il driver se era stato aperto."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
