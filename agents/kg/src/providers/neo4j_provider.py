from configs.settings import settings
from providers.base_provider import BaseProvider

class Neo4jProvider(BaseProvider):
    """Componenti per un grafo Neo4j locale."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.database = database or settings.neo4j_database
        super().__init__()

    def _build_components(self) -> None:
        from connectors.neo4j_connector import Neo4jConnector
        from correctors.error_conditioned_corrector import ErrorConditionedCorrector
        from executors.cypher_executor import CypherExecutor
        from linkers.llm_linker import LLMLinker
        from pruners.neo4j_schema_pruner import Neo4jSchemaPruner
        from translators.cypher_translator import CypherTranslator

        self.executor = CypherExecutor(
            uri=self.uri,
            user=self.user,
            password=self.password,
            database=self.database,
            timeout=settings.neo4j_timeout,
        )
        self.connector = Neo4jConnector(executor=self.executor)
        self.translator = CypherTranslator(self.translation_client)
        self.pruner = Neo4jSchemaPruner()
        self.corrector = ErrorConditionedCorrector(
            self.llm_client,
            prompt_filename="correction_cypher.txt",
            sanitizer=CypherTranslator.sanitize,
        )
        self.linker = LLMLinker(connector=self.connector, llm_client=self.linking_client)
