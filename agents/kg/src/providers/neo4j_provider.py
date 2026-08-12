from configs.settings import settings
from providers.base_provider import BaseProvider

class Neo4jProvider(BaseProvider):
    """Componenti per Neo4j."""

    def _build_components(self) -> None:
        from connectors.neo4j_connector import Neo4jConnector
        from correctors.error_conditioned_corrector import ErrorConditionedCorrector
        from executors.cypher_executor import CypherExecutor
        from linkers.entity_linker import EntityLinker
        from pruners.neo4j_schema_pruner import Neo4jSchemaPruner
        from translators.cypher_translator import CypherTranslator

        self.executor = CypherExecutor(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            timeout=settings.neo4j_timeout,
        )
        self.connector = Neo4jConnector(executor=self.executor)
        self.translator = CypherTranslator(self.translation_client)
        self.pruner = Neo4jSchemaPruner(self.connector)
        self.corrector = ErrorConditionedCorrector(self.translator, self.llm_client)
        self.linker = EntityLinker(connector=self.connector, llm_client=self.linking_client)
