from pathlib import Path

from configs.settings import settings
from providers.base_provider import BaseProvider

_DBPEDIA_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dbpedia_ontology"

class DBpediaProvider(BaseProvider):
    """Componenti per DBpedia."""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or settings.dbpedia_endpoint
        super().__init__()

    def _build_components(self) -> None:
        from connectors.dbpedia_connector import DBpediaConnector
        from correctors.error_conditioned_corrector import ErrorConditionedCorrector
        from executors.sparql_executor import SPARQLExecutor
        from linkers.llm_linker import LLMLinker
        from pruners.vector_pruner import VectorPruner
        from translators.sparql_translator import DBpediaSPARQLTranslator

        self.connector = DBpediaConnector(timeout=settings.dbpedia_timeout)
        self.translator = DBpediaSPARQLTranslator(self.translation_client)
        self.executor = SPARQLExecutor(endpoint=self.endpoint, timeout=settings.dbpedia_timeout)
        self.pruner = VectorPruner(
            index_dir=_DBPEDIA_INDEX_DIR,
            ingest_script="scripts/ingest_dbpedia.py",
        )
        self.corrector = ErrorConditionedCorrector(
            self.llm_client,
            prompt_filename="correction_dbpedia.txt",
            sanitizer=DBpediaSPARQLTranslator.sanitize_sparql,
        )
        self.linker = LLMLinker(connector=self.connector, llm_client=self.linking_client)
