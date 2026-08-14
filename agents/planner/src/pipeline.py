"""
Modulo principale del Planner Agent.
Contiene la logica di orchestrazione (PlannerPipeline) che lega assieme
classificazione del dominio, recupero del contesto, drafting del piano
e validazione/correzione.
"""

import asyncio
import json
import logging
import time
from typing import Any, Literal, get_args

from pydantic import ValidationError

from api.schemas import PlanDay, PlanDomain, QueryRequest, QueryResponse, ResponseDomain, DOMAIN_DESCRIPTIONS
from configs.settings import settings
from llm_client import LLMClient
from state import plan_state_store, StoredPlan
from tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY, query_kg, query_multiapi
from validators import validate_draft

logger = logging.getLogger("planner_pipeline")

# Estraiamo dinamicamente i domini da PlanDomain per evitare "magic strings"
SUPPORTED_DOMAINS = get_args(PlanDomain)


class PlannerPipeline:
    """
    Pipeline dell'agente planner: classifica il dominio, recupera contesto esterno
    (deterministico o tramite tool-calling ReAct per specifici domini), genera 
    una bozza del piano e finalizza la risposta.

    Fasi: 
    1. classify_domain 
    2. gather_context (deterministic o react) 
    3. draft (con validazione e correzione) 
    4. finalize
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Inizializza la pipeline e il client LLM sottostante.

        Args:
            verbose (bool): Se True, abilita la stampa a schermo dei log e dei passaggi.
        """
        self.verbose: bool = verbose
        self.llm: LLMClient = LLMClient(verbose=verbose)
        self._prompts_cache: dict[str, str] = {}

    def _log(self, msg: str, level: int = logging.INFO) -> None:
        """
        Gestisce il logging interno della pipeline.

        Args:
            msg (str): Il messaggio da registrare.
            level (int): Il livello semantico del log (default: logging.INFO).
        """
        if self.verbose:
            print(msg)
        logger.log(level, msg)

    # -- llm helpers ----

    def _load_prompt(self, filename: str) -> str:
        """
        Carica un template prompt dalla cartella prompts, utilizzando una cache in memoria.

        Args:
            filename (str): Il nome del file (es. 'draft_study.txt').

        Returns:
            str: Il contenuto testuale del prompt.
        """
        if filename not in self._prompts_cache:
            path = settings.prompts_dir / filename
            self._prompts_cache[filename] = path.read_text(encoding="utf-8")
        return self._prompts_cache[filename]

    async def _llm_extract_json(self, prompt_file: str, **format_kwargs: Any) -> dict[str, Any] | None:
        """
        Carica il prompt (business-specific), lo formatta e delega dispatch/parsing a LLMClient.

        Args:
            prompt_file (str): Il nome del file di prompt da caricare.
            **format_kwargs (Any): Variabili per formattare il template testuale.

        Returns:
            dict[str, Any] | None: Il JSON estratto come dizionario, o None in caso di errore.
        """
        template: str = self._load_prompt(prompt_file)
        prompt: str = template.format(**format_kwargs)
        return await self.llm.extract_json(prompt)

    # ----- fase 1: classificazione del dominio -----

    async def _classify_domain(self, request: QueryRequest) -> ResponseDomain:
        """
        Classifica la richiesta dell'utente in uno dei domini supportati.

        Args:
            request (QueryRequest): La richiesta in ingresso.

        Returns:
            ResponseDomain: Il dominio individuato (es. 'study', 'travel', 'routine') 
            oppure 'unknown' se fuori scope.
        """
        if request.domain_hint is not None:
            self._log(f"[info] dominio forzato da domain_hint: {request.domain_hint}")
            return request.domain_hint

        self._log("\n[info] [step] classificazione dominio via llm")
        data: dict[str, Any] | None = await self._llm_extract_json(
            "classify_domain.txt", 
            question=request.question,
            domain_descriptions=json.dumps(DOMAIN_DESCRIPTIONS, ensure_ascii=False, indent=2)
        )
        domain: str | None = data.get("domain") if data else None
        
        # Utilizziamo la costante globale derivata da schemas.py 
        if domain in SUPPORTED_DOMAINS:
            self._log(f"  -> dominio classificato: {domain}")
            return domain  # type: ignore

        # Sia 'unknown' che un fallimento di parsing finiscono qui in modo sicuro.
        # Nessun fallback silenzioso su domini a caso che corromperebbe il drafting.
        self._log(
            f"  [warn] dominio non riconosciuto o fuori scope ({domain!r}), classificato come 'unknown'",
            level=logging.WARNING
        )
        return "unknown"

    # ----- fase 2: recupero contesto esterno (deterministico, per dominio) -----

    async def _gather_context(self, domain: PlanDomain, request: QueryRequest) -> tuple[dict[str, Any], list[str]]:
        """
        Recupera il contesto esterno in modo deterministico. Nessuna chiamata
        LLM viene effettuata in questo step per decidere quali tool usare.

        Args:
            domain (PlanDomain): Il dominio del piano classificato al passo 1.
            request (QueryRequest): La richiesta originale.

        Returns:
            tuple[dict[str, Any], list[str]]: Un dizionario di contesto arricchito 
            e una lista di stringhe con i descrittori degli eventuali fallimenti di rete.
        """
        context: dict[str, Any] = {}
        if request.context:
            context.update(request.context)

        errors: list[str] = []

        if domain == "travel":
            self._log("\n[info] [step] recupero contesto esterno (kg-agent + multiapi-agent)")
            kg_result, multiapi_result = await asyncio.gather(
                query_kg(request.question), query_multiapi(request.question)
            )
            
            for key, result in (("kg_agent", kg_result), ("multiapi_agent", multiapi_result)):
                if "error" in result:
                    errors.append(result["error"])
                    self._log(f"  [warn] {key}: {result['error']}", level=logging.WARNING)
                else:
                    # Lista per coerenza di shape con _gather_context_react (che può
                    # accumulare più risposte per lo stesso tool).
                    context[key] = [result]
                    
        # I domini 'study' e 'routine' bypassano la rete: i dati di 'study' sono nel testo,
        # mentre 'routine' non necessita di contesto esterno.

        return context, errors

    async def _gather_context_react(
        self, domain: PlanDomain, request: QueryRequest
    ) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
        """
        Recupera il contesto esterno tramite un loop di tool-calling ReAct (ragionamento 
        e azione). Può eseguire più passi fino al raggiungimento di un esito 'finish'.

        Args:
            domain (PlanDomain): Il dominio del piano.
            request (QueryRequest): La richiesta in ingresso.

        Returns:
            tuple[dict[str, Any], list[str], list[dict[str, Any]]]: Una tripla contenente:
            - il dizionario di contesto arricchito
            - la lista degli errori riscontrati (se presenti)
            - la traccia (trace) con i passaggi del ragionamento LLM
        """
        context: dict[str, Any] = dict(request.context or {})
        errors: list[str] = []
        trace: list[dict[str, Any]] = []
        scratchpad: list[str] = []

        for step in range(settings.max_react_steps):
            decision: dict[str, Any] | None = await self._llm_extract_json(
                "gather_context_react.txt",
                domain=domain, 
                question=request.question,
                scratchpad="\n".join(scratchpad) or "(vuoto)",
                tools=json.dumps(TOOL_DESCRIPTIONS, ensure_ascii=False, indent=2)
            )
            
            if not decision or decision.get("action") not in ("call_tool", "finish"):
                msg: str = f"gather_context_react: decisione non valida al passo {step + 1} ({decision!r}), interrotto"
                self._log(f"  [warn] {msg}", level=logging.WARNING)
                errors.append(msg)
                break
                
            if decision["action"] == "finish":
                self._log(f"  [react] finish - {decision.get('thought', '')}")
                break

            tool_name: str | None = decision.get("tool")
            
            # Usiamo 'or' (e non il default di .get()) perché se l'LLM 
            # restituisce esplicitamente "tool_input": null, dobbiamo bypassarlo.
            tool_input: str = decision.get("tool_input") or request.question
            tool_fn = TOOL_REGISTRY.get(str(tool_name))
            
            obs: dict[str, Any] = (
                {"error": f"tool sconosciuto: {tool_name!r}"} 
                if tool_fn is None 
                else await tool_fn(tool_input)
            )

            trace.append({
                "step": step + 1, 
                "thought": decision.get("thought", ""),
                "tool": tool_name, 
                "tool_input": tool_input, 
                "observation": obs
            })
            
            if "error" in obs:
                errors.append(obs["error"])
            else:
                context.setdefault(str(tool_name), []).append(obs)
                
            scratchpad.append(
                f"Thought: {decision.get('thought','')}\n"
                f"Action: {tool_name}({tool_input})\n"
                f"Observation: {json.dumps(obs, ensure_ascii=False)}"
            )
        else:
            # Raggiunto il limite di iterazioni senza decidere di terminare ('finish')
            msg: str = f"gather_context_react: raggiunto max_react_steps={settings.max_react_steps} senza 'finish'"
            self._log(f"  [warn] {msg}", level=logging.WARNING)
            errors.append(msg)

        return context, errors, trace
    

    # ----- fase 2.5: replanning (modifica di un piano esistente) -----

    async def _classify_intent(self, request: QueryRequest, stored: StoredPlan) -> Literal["new_plan", "replan"]:
        """
        Invocato se esiste già un piano salvato per la sessione corrente.
        Decide se l'utente vuole un piano nuovo o modificare quello in corso.

        Args:
            request (QueryRequest): La richiesta dell'utente.
            stored (StoredPlan): L'oggetto contenente il dominio e la bozza salvati precedentemente.

        Returns:
            Literal["new_plan", "replan"]: L'intento classificato.
        """
        self._log("\n[info] [step] classificazione intento (nuovo piano vs replanning)")
        data: dict[str, Any] | None = await self._llm_extract_json(
            "classify_intent.txt",
            question=request.question,
            domain=stored.domain,
            existing_title=stored.draft.get("title", ""),
        )
        intent: str | None = data.get("intent") if data else None
        
        if intent in ("new_plan", "replan"):
            self._log(f"  -> intento classificato: {intent}")
            return intent  # type: ignore

        # Fallback sicuro: se fallisce, trattiamo come nuovo piano per non
        # alterare accidentalmente quello vecchio.
        self._log(
            f"  [warn] intento non riconosciuto ({intent!r}), fallback su 'new_plan'",
            level=logging.WARNING
        )
        return "new_plan"

    async def _replan(self, request: QueryRequest, stored: StoredPlan) -> tuple[dict[str, Any], int]:
        """
        Genera una bozza aggiornata partendo da un piano già esistente.
        Condivide lo stesso ciclo di validazione/correzione usato da _draft.

        Args:
            request (QueryRequest): La richiesta di modifica dell'utente.
            stored (StoredPlan): Il piano da usare come punto di partenza.

        Returns:
            tuple[dict[str, Any], int]: La bozza modificata e corretta, assieme 
            ai tentativi di retry impiegati.
        """
        self._log(f"\n[info] [step] replanning (dominio={stored.domain}) a partire dallo stato salvato")
        draft: dict[str, Any] | None = await self._llm_extract_json(
            "replan.txt",
            question=request.question,
            domain=stored.domain,
            previous_plan=json.dumps(stored.draft, ensure_ascii=False, indent=2),
        )
        return await self._validate_and_correct(draft, stored.domain, request)
    

    # ----- fase 3: drafting -----

    async def _draft(self, request: QueryRequest, domain: PlanDomain, context: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """
        Genera la bozza iniziale del piano usando il prompt specializzato per il dominio, 
        e ne delega la validazione logica al ciclo di correzione.

        Args:
            request (QueryRequest): La richiesta dell'utente.
            domain (PlanDomain): Il dominio del piano.
            context (dict[str, Any]): Il contesto esterno recuperato al passo precedente.

        Returns:
            tuple[dict[str, Any], int]: La bozza finale corretta e il numero di tentativi spesi.
        """
        self._log(f"\n[info] [step] drafting piano (dominio={domain})")
        draft: dict[str, Any] | None = await self._llm_extract_json(
            f"draft_{domain}.txt",
            question=request.question,
            context=json.dumps(context, ensure_ascii=False, indent=2),
        )
        return await self._validate_and_correct(draft, domain, request)

    async def _validate_and_correct(
        self, draft: dict[str, Any] | None, domain: PlanDomain, request: QueryRequest
    ) -> tuple[dict[str, Any], int]:
        """
        Ciclo di validazione e correzione condiviso per bozze generate ex-novo o aggiornate.
        
        Valida la struttura logica del JSON generato (es. sovrapposizione orari). 
        Se fallisce, rimanda in loop il piano all'LLM assieme agli errori per fixarlo.

        Args:
            draft (dict[str, Any] | None): La bozza (potenzialmente rotta o None) prodotta dal LLM.
            domain (PlanDomain): Il dominio del piano.
            request (QueryRequest): La richiesta originale.

        Returns:
            tuple[dict[str, Any], int]: Il piano valido (o vuoto se irrecuperabile) e il 
            numero di correzioni effettuate.
        """
        errors: list[str] = validate_draft(draft, domain)
        attempt: int = 0

        # Ciclo di retry semantico: invece di fallire subito, chiediamo al LLM 
        # di correggere miratamente gli errori di validazione logica riscontrati.
        while errors and attempt < settings.max_draft_retries:
            attempt += 1
            self._log(
                f"  [warn] draft non conforme (tentativo correzione {attempt}/{settings.max_draft_retries}): {errors}",
                level=logging.WARNING
            )
            draft = await self._llm_extract_json(
                "correct_draft.txt",
                question=request.question,
                errors="; ".join(errors),
                broken_json=json.dumps(draft, ensure_ascii=False) if draft else "null",
            )
            errors = validate_draft(draft, domain)

        if errors:
            self._log(
                f"  [warn] drafting fallito dopo {attempt} correzioni, restituisco struttura vuota. Errori residui: {errors}",
                level=logging.WARNING
            )
            # Rete di sicurezza: non crashiamo l'API, ma restituiamo un piano vuoto e innocuo
            return {"title": request.question, "days": []}, attempt

        self._log(f"  -> draft valido{f' dopo {attempt} correzioni' if attempt else ' al primo tentativo'}")
        
        # type: ignore è sicuro qui perché se errors è vuoto, validate_draft ha confermato 
        # che draft è un dict valido con la struttura base attesa.
        return draft, attempt  # type: ignore


    # ----- fase 4: finalizzazione -----

    def _finalize(
        self,
        request: QueryRequest,
        domain: PlanDomain,
        draft: dict[str, Any],
        elapsed_ms: float,
        draft_attempts: int,
        context: dict[str, Any],
        context_errors: list[str],
        trace: list[dict[str, Any]] | None = None,
        replanned: bool = False,
    ) -> QueryResponse:
        """
        Finalizza il JSON generato dall'LLM, assemblando il QueryResponse. 
        Calcola anche la 'confidence' del risultato basandosi sui tentativi 
        di drafting e sugli eventuali errori di contesto.

        Args:
            request (QueryRequest): La richiesta dell'utente.
            domain (PlanDomain): Il dominio del piano elaborato.
            draft (dict[str, Any]): La bozza grezza corretta restituita dal modello.
            elapsed_ms (float): Tempo totale di esecuzione in millisecondi.
            draft_attempts (int): Tentativi spesi nel ciclo di validazione/correzione.
            context (dict[str, Any]): Contesto arricchito recuperato esternamente.
            context_errors (list[str]): Errori di rete incontrati.
            trace (list[dict[str, Any]] | None): Traccia del loop ReAct (se eseguito).
            replanned (bool): True se è stato aggiornato un piano esistente.

        Returns:
            QueryResponse: L'oggetto di risposta finale validato via Pydantic.
        """
        try:
            days: list[PlanDay] = [PlanDay(**d) for d in draft.get("days", [])]
        except ValidationError as err:
            # Rete di sicurezza: il validatore logico in validators.py opera sul dict 
            # grezzo, se sfugge un disallineamento di tipo allo schema Pydantic
            # non facciamo esplodere la richiesta con un 500. Restituiamo un piano
            # vuoto a bassissima confidence per segnalare l'anomalia.
            self._log(
                f"  [warn] validazione pydantic fallita in finalize nonostante il validatore logico: {err}",
                level=logging.WARNING
            )
            days = []

        # Ogni fallimento di rete resta descritto singolarmente. Lo appendiamo
        # alle note di contingenza eventualmente già pensate dall'LLM.
        contingency_notes: list[str] = list(draft.get("contingency_notes") or [])
        contingency_notes.extend(context_errors)

        if not days:
            confidence: float = 0.0
        else:
            confidence = 1.0 - settings.confidence_retry_penalty * draft_attempts
            if context_errors:
                confidence -= settings.confidence_context_error_penalty
            confidence = round(max(settings.confidence_floor, confidence), 2)

        return QueryResponse(
            question=request.question,
            domain=domain,  # type: ignore
            title=draft.get("title") or request.question,
            summary=draft.get("summary"),
            days=days,
            contingency_notes=contingency_notes or None,
            confidence=confidence,
            execution_time_ms=elapsed_ms,
            gathered_context=context or None,
            tool_calls=trace,
            replanned=replanned,
        )

    # ----- risposta esplicita per richieste fuori scope -----

    def _out_of_scope_response(self, request: QueryRequest, elapsed_ms: float) -> QueryResponse:
        """
        Genera una risposta di chiusura controllata per richieste 
        che non rientrano nei domini del planner.

        Args:
            request (QueryRequest): La richiesta fuori scope.
            elapsed_ms (float): Tempo speso in elaborazione.

        Returns:
            QueryResponse: Una risposta strutturata con un piano vuoto e confidence zero.
        """
        self._log(
            "  [warn] richiesta fuori scope per il planner, nessun drafting eseguito",
            level=logging.WARNING
        )
        return QueryResponse(
            question=request.question,
            domain="unknown",
            title=request.question,
            summary=settings.out_of_scope_message,
            days=[],
            contingency_notes=None,
            confidence=0.0,
            execution_time_ms=elapsed_ms,
        )

    # ----- entrypoint pubblico -----

    async def run(self, request: QueryRequest) -> QueryResponse:
        """
        Esegue l'intera pipeline dell'agente: gestisce sia il replanning 
        su sessioni esistenti, sia la generazione di nuovi piani.

        Args:
            request (QueryRequest): I dati di input forniti all'API.

        Returns:
            QueryResponse: L'output validato pronto per essere inoltrato al client.
        """
        start_time: float = time.time()

        # --- REPLANNING: controllo di un piano esistente salvato in sessione ---
        stored: StoredPlan | None = plan_state_store.get(request.session_id)
        if stored is not None:
            intent: Literal["new_plan", "replan"] = await self._classify_intent(request, stored)
            if intent == "replan":
                draft, draft_attempts = await self._replan(request, stored)
                elapsed_ms: float = round((time.time() - start_time) * 1000, 2)
                response: QueryResponse = self._finalize(
                    request, stored.domain, draft, elapsed_ms, draft_attempts,
                    context={}, context_errors=[], trace=None, replanned=True,
                )
                if draft.get("days"):
                    plan_state_store.save(request.session_id, stored.domain, request.question, draft)
                return response
            # intent == "new_plan": il controllo passa giù alla normale pipeline da zero,
            # che finirà per sovrascrivere lo stato precedente a fine esecuzione.

        # --- PIPELINE NORMALE ---
        domain: ResponseDomain = await self._classify_domain(request)
        if domain == "unknown":
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            return self._out_of_scope_response(request, elapsed_ms)

        # La logica di biforcazione del gathering è legata unicamente
        # alle configurazioni di rete e alla tipologia 'travel'.
        if settings.context_gathering_mode == "react" and domain == "travel":
            context, context_errors, trace = await self._gather_context_react(domain, request)  # type: ignore
        else:
            context, context_errors = await self._gather_context(domain, request)  # type: ignore
            trace = None

        draft, draft_attempts = await self._draft(request, domain, context)  # type: ignore
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        response = self._finalize(
            request, domain, draft, elapsed_ms, draft_attempts, context, context_errors, trace  # type: ignore
        )
        if draft.get("days"):
            plan_state_store.save(request.session_id, domain, request.question, draft)  # type: ignore
        
        return response