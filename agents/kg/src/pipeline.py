import logging
from datetime import datetime, timezone
from typing import Any
from connectors.wikimedia_connector import WikimediaConnector
from linkers.llm_linker import LLMLinker
from translators.sparql_translator import SPARQLTranslator
from executors.sparql_executor import SPARQLExecutor
from correctors.error_conditioned_corrector import ErrorConditionedCorrector
from pruners.khop_pruner import KHopPruner
from cache.semantic_cache import SemanticQueryCache
from configs.settings import settings

logger = logging.getLogger("kg_pipeline")

class KGPipeline:
    """orchestratore principale dell'agente knowledge graph per wikidata."""

    def __init__(
        self,
        connector: Any = None,
        linker: Any = None,
        translator: Any = None,
        executor: Any = None,
        pruner: Any = None,
        corrector: Any = None,
        cache: SemanticQueryCache | None = None,
        verbose: bool = False,
    ):
        self.connector = connector or WikimediaConnector()
        self.linker = linker or LLMLinker(connector=self.connector)
        self.translator = translator or SPARQLTranslator()
        self.executor = executor or SPARQLExecutor()
        self.pruner = pruner or KHopPruner()
        self.corrector = corrector or ErrorConditionedCorrector()
        self.cache = cache or SemanticQueryCache()
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

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
        self._log(f"\n[info] [step] traduzione text2kg (modello: {settings.ollama_model})")
        current_query = self.translator.translate(question=question, schema_context=schema_context)
        self._log("  -> query generata:\n" + "\n".join([f"     {line}" for line in current_query.splitlines()]))

        # esecuzione query con self-correction loop
        self._log("\n[info] [step] esecuzione query & self-correction loop")
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

        # symbol grounding
        self._log("\n[info] [step] symbol grounding & value resolution")
        grounded_results = self.connector.ground_results(raw_results)

        # provenienza
        timestamp = datetime.now(timezone.utc).isoformat()
        for row in grounded_results:
            row["_provenance"] = {
                "source_kg": "wikidata",
                "timestamp": timestamp,
            }

        self.cache.set(question=question, query=current_query, results=grounded_results)
        return grounded_results, current_query
