import logging
import re
import time
from datetime import datetime, timezone
from typing import NamedTuple

from cache.semantic_cache import SemanticQueryCache
from configs.settings import settings
from linkers.base_linker import BaseLinker
from providers.base_provider import BaseProvider

logger = logging.getLogger("kg_pipeline")

class PipelineResult(NamedTuple):
    """Esito di KGPipeline.run(): risultati grounded, query eseguita, confidenza euristica."""
    results: list[dict]
    query: str
    confidence: float
    cached: bool = False

def build_provider(target_kg: str) -> BaseProvider:
    """Istanzia il provider del KG richiesto. Solleva ValueError se il KG non è supportato."""
    # import lazy: ogni provider costruisce risorse pesanti (indice FAISS, driver bolt)
    # e importarli tutti richiederebbe ogni dipendenza anche usando un solo KG
    kg = (target_kg or "").strip().lower()

    if kg in ("", "wikidata"):
        from providers.wikidata_provider import WikidataProvider
        return WikidataProvider()
    if kg == "neo4j":
        from providers.neo4j_provider import Neo4jProvider
        return Neo4jProvider()
    if kg == "dbpedia":
        from providers.dbpedia_provider import DBpediaProvider
        return DBpediaProvider()

    raise ValueError(
        f"knowledge graph non supportato: '{target_kg}'. "
        f"valori ammessi: 'wikidata', 'dbpedia', 'neo4j'."
    )

class KGPipeline:
    """Orchestratore dell'agente: linking, pruning, traduzione, esecuzione e grounding."""

    def __init__(
        self,
        provider: BaseProvider | None = None,
        linker: BaseLinker | None = None,
        cache: SemanticQueryCache | None = None,
        target_kg: str = settings.default_target_kg,
        verbose: bool = False,
    ) -> None:
        self.target_kg = target_kg
        self.provider = provider or build_provider(target_kg)
        self.connector = self.provider.get_connector()
        self.translator = self.provider.get_translator()
        self.executor = self.provider.get_executor()
        self.pruner = self.provider.get_pruner()
        self.corrector = self.provider.get_corrector()
        self.linker = linker or self.provider.get_linker()
        self.cache = cache or SemanticQueryCache()
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
        logger.info(msg)

    def _log_query(self, prefix: str, query: str) -> None:
        """Registra una query indentandone le righe, per leggibilità nei log."""
        self._log(prefix + "\n" + "\n".join(f"     {line}" for line in query.splitlines()))

    def _execute_with_correction(
        self, current_query: str, question: str, schema_context: str = ""
    ) -> tuple[list[dict], str, int]:
        """Esegue la query correggendola in caso di errore; restituisce anche i tentativi usati."""
        raw_results = None
        last_error = None
        max_retries = settings.max_correction_retries
        attempts_used = 0

        for attempt in range(max_retries + 1):
            attempts_used = attempt + 1
            try:
                raw_results = self.executor.execute(current_query)
                self._log(f"  -> esecuzione riuscita al tentativo {attempt + 1}. trovate {len(raw_results)} righe grezze.")
                break
            except Exception as err:
                last_error = err
                self._log(f"  [warn] errore durante l'esecuzione (tentativo {attempt + 1}/{max_retries + 1}): {err}")
                if not (attempt < max_retries and self.corrector):
                    raise

                # su rate limit e timeout la query è valida: basta attendere e riprovare
                err_str = str(err).lower()
                if any(k in err_str for k in ("429", "timeout", "rate limit", "502", "503")):
                    self._log(f"  [retry] rate limit o timeout rilevato, attesa {2.0 * (attempt + 1)}s...")
                    time.sleep(2.0 * (attempt + 1))
                    continue

                self._log("  [retry] attivazione self-correction loop...")
                current_query = self.corrector.correct(
                    question=question,
                    failed_query=current_query,
                    error_message=str(err),
                    schema_context=schema_context,
                )
                self._log_query("  -> query corretta dal modello:", current_query)

        if raw_results is None and last_error is not None:
            raise last_error

        return raw_results, current_query, attempts_used

    def _validate_and_retry(
        self, raw_results: list[dict], current_query: str, question: str, schema_context: str
    ) -> tuple[list[dict], str, bool]:
        """Validazione ReAct: se i risultati sono vuoti rigenera la query con feedback."""
        if raw_results:
            return raw_results, current_query, False

        self._log("\n[info] [step] react validation: risultati vuoti")

        # tentativo economico prima di scomodare l'LLM: un filtro di tipo superfluo è una
        # causa strutturale frequente di zero righe (vedi relax_class_filters)
        relax = getattr(self.translator, "relax_class_filters", None)
        relaxed_query = relax(current_query) if relax else None
        if relaxed_query:
            self._log_query("  -> rilevato filtro di classe superfluo, riprovo alleggerita:", relaxed_query)
            try:
                relaxed_results, relaxed_query, _ = self._execute_with_correction(
                    relaxed_query, question, schema_context=schema_context
                )
                if relaxed_results:
                    return relaxed_results, relaxed_query, True
            except Exception as err:
                self._log(f"  [warn] query alleggerita fallita: {err}")

        self._log("\n[info] [step] rigenerazione query con feedback")
        feedback = self.translator.generate_feedback_prompt(
            query=current_query,
            schema_context=schema_context,
        )
        retry_query = self.translator.translate(question=question, schema_context=feedback)
        self._log_query("  -> query rigenerata:", retry_query)

        try:
            retry_results, retry_query, _ = self._execute_with_correction(
                retry_query, question, schema_context=schema_context
            )
            if retry_results:
                return retry_results, retry_query, True
        except Exception as err:
            self._log(f"  [warn] rigenerazione fallita: {err}")

        return raw_results, current_query, True

    @staticmethod
    def _compute_confidence(results: list[dict], correction_attempts: int, react_retry_used: bool) -> float:
        """Confidenza euristica dedotta da quanta fatica è servita per ottenere il risultato."""
        # non è una probabilità calibrata: penalizza le correzioni e le rigenerazioni,
        # che segnalano una traduzione iniziale imprecisa
        if not results:
            return 0.0

        confidence = 1.0
        if correction_attempts > 1:
            confidence -= 0.2 * (correction_attempts - 1)
        if react_retry_used:
            confidence -= 0.3
        return max(0.0, min(1.0, confidence))

    def _relation_query(self, question: str, entities: list) -> str:
        """Rimuove dalla domanda le menzioni già risolte, lasciando la sola parte relazionale."""
        # il nome proprio inquina la ricerca vettoriale: con "president of Real Madrid"
        # la proprietà "chairperson" scivola dal 2° al 25° posto
        relation_query = question
        for ent in entities:
            relation_query = re.sub(re.escape(ent.mention), " ", relation_query, flags=re.IGNORECASE)
        relation_query = re.sub(r"'s\b", "", relation_query)
        return re.sub(r"\s+", " ", relation_query).strip()

    def run(self, question: str) -> PipelineResult:
        """Esegue la pipeline agentica sulla domanda e restituisce i risultati grounded."""
        self._log("\n[info] [step] verifica semantic cache")
        if self.cache:
            cached = self.cache.get(question)
            if cached:
                self._log("  -> cache hit! restituisco i risultati salvati.")
                cached_query, cached_results, cached_confidence = cached
                return PipelineResult(cached_results, cached_query, cached_confidence, cached=True)

        self._log("\n[info] [step] entity linking")
        entities = self.linker.link(question)
        for ent in entities:
            self._log(f"  -> menzionato: '{ent.mention}' -> associato a id: [{ent.id}] (label: '{ent.label}')")
        seed_ids = [ent.id for ent in entities if ent.id]

        self._log("\n[info] [step] schema retrieval")
        relation_query = self._relation_query(question, entities)
        pruned_schema = self.pruner.prune(
            seed_entity_ids=seed_ids,
            connector_or_client=self.connector,
            max_items=25,
            question=relation_query or question,
        )
        schema_context = pruned_schema.context_text
        if not schema_context:
            schema_context = "\n".join(f"entità: {ent.label} (id:{ent.id})" for ent in entities)
        self._log_query("  -> schema prunato fornito al modello:", "\n".join(schema_context.splitlines()[:5]))

        self._log(f"\n[info] [step] traduzione text2kg (modello: {self.translator.llm_client.model_name})")
        current_query = self.translator.translate(question=question, schema_context=schema_context)
        self._log_query("  -> query generata:", current_query)

        self._log("\n[info] [step] esecuzione query & self-correction loop")
        raw_results, current_query, correction_attempts = self._execute_with_correction(
            current_query, question, schema_context=schema_context
        )
        raw_results, current_query, react_retry_used = self._validate_and_retry(
            raw_results, current_query, question, schema_context
        )

        self._log("\n[info] [step] symbol grounding & value resolution")
        grounded_results = self.connector.ground_results(raw_results)

        timestamp = datetime.now(timezone.utc).isoformat()
        for row in grounded_results:
            row["_provenance"] = {"source_kg": self.target_kg, "timestamp": timestamp}

        confidence = self._compute_confidence(grounded_results, correction_attempts, react_retry_used)
        if self.cache and grounded_results:
            self.cache.set(
                question=question,
                query=current_query,
                results=grounded_results,
                confidence=confidence,
            )
        return PipelineResult(grounded_results, current_query, confidence)
