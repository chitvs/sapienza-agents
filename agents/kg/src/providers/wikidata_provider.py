from configs.settings import settings
from providers.base_provider import BaseProvider

class WikidataProvider(BaseProvider):
    """Componenti per Wikidata."""

    def _build_components(self) -> None:
        from connectors.wikidata_connector import WikidataConnector
        from correctors.error_conditioned_corrector import ErrorConditionedCorrector
        from executors.sparql_executor import SPARQLExecutor
        from linkers.entity_linker import EntityLinker
        from pruners.vector_pruner import VectorPruner
        from translators.sparql_translator import WikidataSPARQLTranslator

        self.connector = WikidataConnector()
        self.translator = WikidataSPARQLTranslator(self.translation_client)
        self.executor = SPARQLExecutor(
            endpoint=settings.wikidata_endpoint,
            timeout=settings.wikidata_timeout,
        )
        self.pruner = VectorPruner(self.connector)
        self.corrector = ErrorConditionedCorrector(self.translator, self.llm_client)
        self.linker = EntityLinker(connector=self.connector, llm_client=self.linking_client)
