from pathlib import Path
from configs.settings import settings
from connectors.dbpedia_connector import DBpediaConnector
from correctors.error_conditioned_corrector import ErrorConditionedCorrector
from executors.sparql_executor import SPARQLExecutor
from linkers.entity_linker import EntityLinker
from providers.base_provider import BaseProvider
from pruners.vector_pruner import VectorPruner
from translators.sparql_translator import DBpediaSPARQLTranslator

_DBPEDIA_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dbpedia_ontology"

class DBpediaProvider(BaseProvider):
    """Componenti per DBpedia."""

    def _build_components(self) -> None:
        self.connector = DBpediaConnector()
        self.translator = DBpediaSPARQLTranslator(self.translation_client)
        self.executor = SPARQLExecutor(endpoint=settings.dbpedia_endpoint, timeout=settings.dbpedia_timeout)
        self.pruner = VectorPruner(
            self.connector, index_dir=_DBPEDIA_INDEX_DIR, ingest_script="scripts/ingest_dbpedia.py"
        )
        self.corrector = ErrorConditionedCorrector(self.translator, self.llm_client)
        self.linker = EntityLinker(connector=self.connector, llm_client=self.linking_client)
