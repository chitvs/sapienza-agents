from configs.settings import settings
from providers.base_provider import BaseProvider

class WikidataProvider(BaseProvider):
    """Componenti per Wikidata."""

    def _build_components(self) -> None:
        from connectors.wikimedia_connector import WikimediaConnector
        from correctors.error_conditioned_corrector import ErrorConditionedCorrector
        from executors.sparql_executor import SPARQLExecutor
        from linkers.llm_linker import LLMLinker
        from pruners.vector_pruner import VectorPruner
        from translators.sparql_translator import WikidataSPARQLTranslator

        self.connector = WikimediaConnector()
        self.translator = WikidataSPARQLTranslator(self.translation_client)
        self.executor = SPARQLExecutor(
            endpoint=settings.sparql_endpoint,
            timeout=settings.sparql_timeout,
        )
        self.pruner = VectorPruner()
        self.corrector = ErrorConditionedCorrector(self.llm_client)
        self.linker = LLMLinker(connector=self.connector, llm_client=self.linking_client)
