import logging
import re
import time
from datetime import datetime, timezone
from typing import NamedTuple

from cache.base_cache import BaseCache
from cache.semantic_cache import SemanticCache
from configs.settings import settings
from connectors.base_connector import KnowledgeGraphUnavailableError
from executors.base_executor import QueryExecutionError
from providers import build_provider
from providers.base_provider import BaseProvider

logger = logging.getLogger("kg_pipeline")

def _is_infrastructure_failure(err: Exception) -> bool:
    """Distingue un guasto del knowledge graph da una query che il modello ha sbagliato."""
    if isinstance(err, KnowledgeGraphUnavailableError):
        return True
    return isinstance(err, QueryExecutionError) and err.retryable

class PipelineResult(NamedTuple):
    """Esito di KGPipeline.run(): risultati grounded, query eseguita, confidenza euristica."""
    results: list[dict]
    query: str
    confidence: float
    cached: bool = False

class KGPipeline:
    """Orchestratore dell'agente: linking, pruning, traduzione, esecuzione e grounding."""

    def __init__(
        self,
        provider: BaseProvider | None = None,
        cache: BaseCache | None = None,
        target_kg: str = settings.default_target_kg,
    ) -> None:
        self.target_kg = target_kg
        self.provider = provider or build_provider(target_kg)
        self.connector = self.provider.connector
        self.translator = self.provider.translator
        self.executor = self.provider.executor
        self.pruner = self.provider.pruner
        self.corrector = self.provider.corrector
        self.linker = self.provider.linker
        self.cache = cache or SemanticCache()

    @staticmethod
    def _log_query(prefix: str, query: str) -> None:
        """Registra una query indentandone le righe, per leggibilità nei log."""
        logger.info(prefix + "\n" + "\n".join(f"     {line}" for line in query.splitlines()))

    def _execute_with_correction(
        self, current_query: str, question: str, schema_context: str = ""
    ) -> tuple[list[dict], str, int]:
        """Esegue la query correggendola in caso di errore; restituisce anche le correzioni usate."""
        max_retries = settings.max_correction_retries
        # si contano le sole correzioni, non i giri totali: un 503 dell'endpoint non dice
        # nulla sulla qualità della traduzione e non deve abbassare la confidenza
        corrections_used = 0

        for attempt in range(max_retries + 1):
            try:
                raw_results = self.executor.execute(current_query)
                logger.info(f"  -> esecuzione riuscita al tentativo {attempt + 1}. trovate {len(raw_results)} righe grezze.")
                return raw_results, current_query, corrections_used
            except QueryExecutionError as err:
                logger.info(f"  [warn] errore durante l'esecuzione (tentativo {attempt + 1}/{max_retries + 1}): {err}")
                if not (attempt < max_retries and self.corrector):
                    raise

                # la query è valida e il guasto è transitorio: si ripete identica
                if err.retryable:
                    backoff = settings.retry_backoff_seconds * (attempt + 1)
                    logger.info(f"  [retry] guasto transitorio dell'endpoint, attesa {backoff}s...")
                    time.sleep(backoff)
                    continue

                corrections_used += 1
                logger.info("  [retry] attivazione self-correction loop...")
                current_query = self.corrector.correct(
                    question=question,
                    failed_query=current_query,
                    error_message=str(err),
                    schema_context=schema_context,
                )
                self._log_query("  -> query corretta dal modello:", current_query)

    def _validate_and_retry(
        self, raw_results: list[dict], current_query: str, question: str, schema_context: str
    ) -> tuple[list[dict], str, bool]:
        """Validazione ReAct: se i risultati sono vuoti rigenera la query con feedback."""
        if raw_results:
            return raw_results, current_query, False

        logger.info("\n[info] [step] react validation: risultati vuoti")

        # tentativo economico prima di scomodare l'LLM: un vincolo superfluo è una causa
        # strutturale frequente di zero righe (vedi relax_constraints)
        relaxed_query = self.translator.relax_constraints(current_query)
        if relaxed_query:
            self._log_query("  -> rilevato filtro di classe superfluo, riprovo alleggerita:", relaxed_query)
            try:
                relaxed_results, relaxed_query, _ = self._execute_with_correction(
                    relaxed_query, question, schema_context=schema_context
                )
                if relaxed_results:
                    return relaxed_results, relaxed_query, True
            except Exception as err:
                if _is_infrastructure_failure(err):
                    raise
                logger.info(f"  [warn] query alleggerita fallita: {err}")

        logger.info("\n[info] [step] rigenerazione query con feedback")
        try:
            feedback = self.translator.generate_feedback_prompt(
                query=current_query,
                schema_context=schema_context,
            )
            retry_query = self.translator.translate(
                question=question,
                schema_context=feedback,
                temperature=settings.retry_temperature,
                top_p=settings.retry_top_p,
            )
            self._log_query("  -> query rigenerata:", retry_query)

            retry_results, retry_query, _ = self._execute_with_correction(
                retry_query, question, schema_context=schema_context
            )
            if retry_results:
                return retry_results, retry_query, True
        except Exception as err:
            if _is_infrastructure_failure(err):
                raise
            logger.info(f"  [warn] rigenerazione fallita: {err}")

        return raw_results, current_query, True

    @staticmethod
    def _compute_confidence(results: list[dict], corrections_used: int, react_retry_used: bool) -> float:
        """Confidenza euristica dedotta da quanta fatica è servita per ottenere il risultato."""
        # penalizza le correzioni e le rigenerazioni, che segnalano una traduzione
        # iniziale imprecisa. I ritentativi per guasto transitorio dell'endpoint
        # non contano perchè misurerebbero la rete, non la traduzione.
        if not results:
            return 0.0

        confidence = 1.0 - 0.2 * corrections_used
        if react_retry_used:
            confidence -= 0.3
        return max(0.0, min(1.0, confidence))

    def _relation_query(self, question: str, entities: list) -> str:
        """Rimuove dalla domanda le menzioni già risolte, lasciando la sola parte relazionale."""
        # il nome proprio inquina la ricerca vettoriale: con "president of Real Madrid"
        # la proprietà "chairperson" scivola dal 2° al 25° posto
        relation_query = question
        for ent in entities:
            # i confini di parola sono indispensabili: senza, il film "Her" cancella le
            # tre lettere centrali di "Where" e la ricerca vettoriale riceve rumore
            pattern = rf"(?<!\w){re.escape(ent.mention)}(?!\w)"
            relation_query = re.sub(pattern, " ", relation_query, flags=re.IGNORECASE)
        relation_query = re.sub(r"'s\b", "", relation_query)
        return re.sub(r"\s+", " ", relation_query).strip()

    def run(self, question: str) -> PipelineResult:
        """Esegue la pipeline agentica sulla domanda e restituisce i risultati grounded."""
        logger.info("\n[info] [step] verifica semantic cache")
        cached = self.cache.get(question)
        if cached:
            logger.info("  -> cache hit! restituisco i risultati salvati.")
            cached_query, cached_results, cached_confidence = cached
            return PipelineResult(cached_results, cached_query, cached_confidence, cached=True)

        logger.info("\n[info] [step] entity linking")
        entities = self.linker.link(question)
        for ent in entities:
            logger.info(f"  -> menzionato: '{ent.mention}' -> associato a id: [{ent.id}] (label: '{ent.label}')")
        seed_ids = [ent.id for ent in entities if ent.id]

        logger.info("\n[info] [step] schema retrieval")
        relation_query = self._relation_query(question, entities)
        pruned_schema = self.pruner.prune(
            seed_entity_ids=seed_ids,
            question=relation_query or question,
        )
        schema_context = pruned_schema.context_text
        if not schema_context:
            schema_context = "\n".join(f"entità: {ent.label} (id:{ent.id})" for ent in entities)
        self._log_query("  -> schema prunato fornito al modello:", "\n".join(schema_context.splitlines()[:5]))

        logger.info(f"\n[info] [step] traduzione text2kg (modello: {self.translator.llm_client.model_name})")
        current_query = self.translator.translate(question=question, schema_context=schema_context)
        self._log_query("  -> query generata:", current_query)

        logger.info("\n[info] [step] esecuzione query & self-correction loop")
        raw_results, current_query, corrections_used = self._execute_with_correction(
            current_query, question, schema_context=schema_context
        )
        raw_results, current_query, react_retry_used = self._validate_and_retry(
            raw_results, current_query, question, schema_context
        )

        logger.info("\n[info] [step] symbol grounding & value resolution")
        grounded_results = self.connector.ground_results(raw_results)

        timestamp = datetime.now(timezone.utc).isoformat()
        for row in grounded_results:
            row["_provenance"] = {"source_kg": self.target_kg, "timestamp": timestamp}

        confidence = self._compute_confidence(grounded_results, corrections_used, react_retry_used)
        if grounded_results:
            self.cache.set(
                question=question,
                query=current_query,
                results=grounded_results,
                confidence=confidence,
            )
        return PipelineResult(grounded_results, current_query, confidence)
