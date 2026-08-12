import re
from typing import Any

from executors.base_executor import BaseExecutor, QueryExecutionError
from query_text import mask_literals

class CypherExecutionError(QueryExecutionError):
    """Errore durante la validazione o l'esecuzione di una query Cypher."""

class CypherExecutor(BaseExecutor):
    """Esegue query Cypher su Neo4j, rifiutando tutto ciò che non sia sola lettura."""

    _WRITE_CLAUSES = (
        (r"CREATE\b", "CREATE"), (r"MERGE\b", "MERGE"), (r"DELETE\b", "DELETE"),
        (r"DETACH\b", "DETACH"), (r"SET\b", "SET"), (r"REMOVE\b", "REMOVE"),
        (r"DROP\b", "DROP"), (r"LOAD\s+CSV\b", "LOAD CSV"), (r"FOREACH\b", "FOREACH"),
        (r"CALL\s*\{", "CALL {"), (r"TERMINATE\b", "TERMINATE"),
    )

    _ALLOWED_PROCEDURES = (
        "db.labels", "db.relationshiptypes", "db.propertykeys",
        "db.schema.visualization", "db.schema.nodetypeproperties", "db.schema.reltypeproperties",
    )

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        timeout: float,
        database: str | None = None,
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
        """Solleva CypherExecutionError se la query contiene clausole o procedure di scrittura."""
        # le occorrenze dentro stringhe letterali non contano: un film intitolato
        # "CREATE OR DELETE" non deve far scattare il controllo
        without_literals = mask_literals(query)

        for pattern, clause in cls._WRITE_CLAUSES:
            if re.search(rf"(?<![.:\w]){pattern}", without_literals, flags=re.IGNORECASE):
                raise CypherExecutionError(
                    f"SYNTAX_ERROR: la query contiene la clausola di scrittura '{clause}', "
                    f"ma questo agente può solo leggere dal grafo. Riscrivere la query "
                    f"usando esclusivamente MATCH/OPTIONAL MATCH/WHERE/RETURN.",
                    query=query,
                )

        for match in re.finditer(r"\bCALL\s+([\w.]+)", without_literals, flags=re.IGNORECASE):
            if match.group(1).lower() not in cls._ALLOWED_PROCEDURES:
                raise CypherExecutionError(
                    f"SYNTAX_ERROR: la procedura '{match.group(1)}' non è fra quelle di sola "
                    f"lettura ammesse. Riscrivere la query usando esclusivamente "
                    f"MATCH/OPTIONAL MATCH/WHERE/RETURN.",
                    query=query,
                )

    def _run_with_params(self, query: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Esegue la query in una transazione di sola lettura."""
        try:
            from neo4j.exceptions import Neo4jError, ServiceUnavailable
        except ImportError:
            Neo4jError = ServiceUnavailable = ()  # type: ignore[assignment, misc]

        session_kwargs = {"database": self.database} if self.database else {}

        try:
            driver = self._get_driver()
            with driver.session(default_access_mode="READ", **session_kwargs) as session:
                # il timeout va sulla transazione: passato a run() diventerebbe un
                # parametro della query anziché un limite di tempo
                with session.begin_transaction(timeout=self.timeout) as tx:
                    return [record.data() for record in tx.run(query, params or {})]
        except CypherExecutionError:
            raise
        except ServiceUnavailable as err:
            raise CypherExecutionError(
                f"neo4j non raggiungibile su {self.uri}: {err}", query=query, retryable=True
            ) from err
        except Neo4jError as err:
            raise CypherExecutionError(str(err), query=query) from err
        except Exception as err:
            raise CypherExecutionError(f"errore durante l'esecuzione: {err}", query=query) from err

    def execute_trusted(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Query di servizio scritta da noi: salta il controllo di keyword, non la guardia di sola lettura."""
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
