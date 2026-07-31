import logging
from datetime import datetime, timezone
from typing import Any
from connectors.base_connector import BaseConnector
from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import BaseLinker
from linkers.llm_linker import LLMLinker
from translators.sparql_translator import SPARQLTranslator
from executors.base_executor import BaseExecutor
from executors.sparql_executor import SPARQLExecutor
from correctors.error_conditioned_corrector import ErrorConditionedCorrector
from pruners.base_pruner import BasePruner
from pruners.khop_pruner import KHopPruner
from pruners.relevance_pruner import RelevancePruner
from cache.semantic_cache import SemanticQueryCache
from configs.settings import settings

logger = logging.getLogger("kg_pipeline")

class KGPipeline:
    """orchestratore principale dell'agente knowledge graph per wikidata."""

    def __init__(
        self,
        connector: BaseConnector | None = None,
        linker: BaseLinker | None = None,
        translator: SPARQLTranslator | None = None,
        executor: BaseExecutor | None = None,
        pruner: BasePruner | None = None,
        corrector: ErrorConditionedCorrector | None = None,
        cache: SemanticQueryCache | None = None,
        target_kg: str = "wikidata",
        verbose: bool = False,
    ):
        self.target_kg = target_kg
        self.connector = connector or WikimediaConnector()
        self.linker = linker or LLMLinker(connector=self.connector)
        self.translator = translator or SPARQLTranslator()
        self.executor = executor or SPARQLExecutor()
        self.pruner = pruner or RelevancePruner()
        self.corrector = corrector or ErrorConditionedCorrector()
        self.cache = cache or SemanticQueryCache()
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    def _execute_with_correction(self, current_query: str, question: str) -> tuple[list[dict], str]:
        """esegue la query con self-correction loop in caso di errore."""
        raw_results = None
        last_error = None
        max_retries = settings.max_correction_retries

        for attempt in range(max_retries + 1):
            try:
                raw_results = self.executor.execute(current_query)
                self._log(f"  -> esecuzione riuscita al tentativo {attempt + 1}. trovate {len(raw_results)} righe grezze.")
                break
            except Exception as err:
                last_error = err
                self._log(f"  [warn] errore durante l'esecuzione (tentativo {attempt + 1}/{max_retries + 1}): {err}")
                if attempt < max_retries and self.corrector:
                    self._log("  [retry] attivazione self-correction loop...")
                    current_query = self.corrector.correct(
                        question=question,
                        failed_query=current_query,
                        error_message=str(err),
                    )
                    self._log("  -> query corretta dal modello:\n" + "\n".join([f"     {line}" for line in current_query.splitlines()]))
                else:
                    raise err

        if raw_results is None and last_error is not None:
            raise last_error

        return raw_results, current_query

    def _validate_and_retry(self, raw_results: list[dict], current_query: str, question: str, schema_context: str) -> tuple[list[dict], str]:
        """validazione react: se i risultati sono vuoti, rigenera la query con feedback."""
        if raw_results:
            return raw_results, current_query

        self._log("\n[info] [step] react validation: risultati vuoti, rigenerazione query con feedback")

        feedback = (
            f"the previous SPARQL query returned 0 results:\n{current_query}\n\n"
            f"try a different approach. consider using SERVICE wikibase:label, "
            f"schema:description, or different properties from the schema context.\n\n"
            f"schema context:\n{schema_context}"
        )

        retry_query = self.translator.translate(
            question=question,
            schema_context=feedback,
        )
        self._log("  -> query rigenerata:\n" + "\n".join([f"     {line}" for line in retry_query.splitlines()]))

        try:
            retry_results, retry_query = self._execute_with_correction(retry_query, question)
            if retry_results:
                return retry_results, retry_query
        except Exception as err:
            self._log(f"  [warn] rigenerazione fallita: {err}")

        return raw_results, current_query

    def run(self, question: str) -> tuple[list[dict], str]:
        """esegue la pipeline agentica per wikidata con log strutturati."""
        self._log("\n[info] [step] verifica semantic cache")
        cached_result = self.cache.get(question)
        if cached_result:
            self._log("  -> match trovato in semantic query cache.")
            return cached_result[1], cached_result[0]

        # entity linking
        self._log("\n[info] [step] entity linking")
        entities = self.linker.link(question)
        for ent in entities:
            qid = getattr(ent, "qid", getattr(ent, "id", ""))
            self._log(f"  -> menzionato: '{ent.mention}' -> associato a id: [{qid}] (label: '{ent.label}')")

        seed_ids = [getattr(ent, "qid", getattr(ent, "id", "")) for ent in entities if getattr(ent, "qid", getattr(ent, "id", ""))]

        # dynamic schema pruning
        self._log("\n[info] [step] dynamic schema pruning (contesto k-hop)")
        pruned_schema = self.pruner.prune(seed_entity_ids=seed_ids, connector_or_client=self.connector, question=question)
        schema_context = pruned_schema.context_text
        if not schema_context:
            context_items = [f"entità: {ent.label} (id:{getattr(ent, 'qid', getattr(ent, 'id', ''))})" for ent in entities]
            schema_context = "\n".join(context_items)

        self._log("  -> schema prunato fornito al modello:\n" + "\n".join([f"     {line}" for line in schema_context.splitlines()[:5]]))

        # traduzione text2kg
        self._log(f"\n[info] [step] traduzione text2kg (modello: {settings.ollama_translation_model})")
        current_query = self.translator.translate(question=question, schema_context=schema_context)
        self._log("  -> query generata:\n" + "\n".join([f"     {line}" for line in current_query.splitlines()]))

        # esecuzione query con self-correction loop
        self._log("\n[info] [step] esecuzione query & self-correction loop")
        raw_results, current_query = self._execute_with_correction(current_query, question)

        # react validation: rigenera se risultati vuoti
        raw_results, current_query = self._validate_and_retry(raw_results, current_query, question, schema_context)

        # symbol grounding
        self._log("\n[info] [step] symbol grounding & value resolution")
        grounded_results = self.connector.ground_results(raw_results)

        # provenienza
        timestamp = datetime.now(timezone.utc).isoformat()
        for row in grounded_results:
            row["_provenance"] = {
                "source_kg": self.target_kg,
                "timestamp": timestamp,
            }

        self.cache.set(question=question, query=current_query, results=grounded_results)
        return grounded_results, current_query
