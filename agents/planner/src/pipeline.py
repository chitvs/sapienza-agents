"""
Modulo principale del Planner Agent.
Contiene la logica di orchestrazione (PlannerPipeline) che lega assieme
classificazione del dominio, recupero del contesto, drafting del piano
e validazione/correzione.
"""

import json
import logging
import time
from typing import Any, Literal, get_args

from pydantic import ValidationError

from api.schemas import PlanDay, PlanDomain, QueryRequest, QueryResponse, ResponseDomain, DOMAIN_DESCRIPTIONS
from configs.settings import settings
from llm_client import LLMClient
from validators import validate_draft

from context_gathering import ContextGatherer
from events import EventCallback, EventStatus, emit
from logging_utils import make_logger
from prompts import PromptLibrary

logger = logging.getLogger("planner_pipeline")

# Estraiamo dinamicamente i domini da PlanDomain per evitare "magic strings"
SUPPORTED_DOMAINS = get_args(PlanDomain)

REPLAN_FAILURE_NOTE: str = "Non sono riuscito ad applicare le modifiche richieste mantenendo il piano coerente."


class PlannerPipeline:
    """
    Pipeline dell'agente planner: classifica il dominio, recupera contesto esterno,
    genera una bozza del piano e finalizza la risposta gestendo validazione e correzione.
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Inizializza la pipeline, il client LLM, il gestore dei prompt e il context gatherer.

        Args:
            verbose (bool): Se True, abilita la stampa a schermo dei log e dei passaggi per debug.
        """
        self.verbose: bool = verbose
        self._log = make_logger(logger, verbose)
        
        self.llm: LLMClient = LLMClient(verbose=verbose)
        self.prompts: PromptLibrary = PromptLibrary()
        self.context_gatherer: ContextGatherer = ContextGatherer(prompts=self.prompts, verbose=verbose)

    # ----- fase 1: classificazione del dominio -----

    async def _classify_domain(
        self, 
        request: QueryRequest, 
        llm: LLMClient, 
        on_event: EventCallback | None = None
    ) -> ResponseDomain:
        """
        Classifica la richiesta dell'utente in uno dei domini supportati.

        Args:
            request (QueryRequest): La richiesta in ingresso.
            llm (LLMClient): Istanza del client LLM da interrogare.
            on_event (EventCallback | None): Callback per la notifica SSE dello stato.

        Returns:
            ResponseDomain: Il dominio individuato (es. 'study', 'travel', 'routine') 
            oppure 'unknown' se fuori scope.
        """
        if request.domain_hint is not None:
            self._log(f"[info] dominio forzato da domain_hint: {request.domain_hint}")
            await emit(on_event, EventStatus.DOMAIN_CLASSIFIED, f"Dominio forzato: {request.domain_hint}", domain=request.domain_hint)
            return request.domain_hint
        
        self._log("\n[info] [step] classificazione dominio via llm")
        await emit(on_event, EventStatus.CLASSIFYING_DOMAIN, "Classificazione del dominio in corso")
        
        data = await self.prompts.extract_json(
            "classify_domain.txt", 
            llm,
            question=request.question,
            domain_descriptions=json.dumps(DOMAIN_DESCRIPTIONS, ensure_ascii=False, indent=2),
        )
        domain: str | None = data.get("domain") if data else None
        
        if domain in SUPPORTED_DOMAINS:
            self._log(f"  -> dominio classificato: {domain}")
            await emit(on_event, EventStatus.DOMAIN_CLASSIFIED, f"Dominio identificato: {domain}", domain=domain)
            return domain  # type: ignore

        # Fallback sicuro in caso di dominio sconosciuto o fallimento del parsing LLM.
        self._log(
            f"  [warn] dominio non riconosciuto o fuori scope ({domain!r}), classificato come 'unknown'",
            level=logging.WARNING
        )
        await emit(on_event, EventStatus.DOMAIN_CLASSIFIED, "Richiesta fuori scope per il planner", domain="unknown")
        return "unknown"

    # ----- fase 2: replanning (modifica di un piano esistente) -----

    async def _replan(
        self, 
        request: QueryRequest, 
        llm: LLMClient, 
        on_event: EventCallback | None = None
    ) -> tuple[dict[str, Any], int]:
        """
        Genera una bozza aggiornata partendo da un piano già esistente.

        Args:
            request (QueryRequest): La richiesta di modifica dell'utente.
            llm (LLMClient): Istanza del client LLM da interrogare.
            on_event (EventCallback | None): Callback per notifica SSE.

        Returns:
            tuple[dict[str, Any], int]: La bozza modificata/corretta e il numero di tentativi di retry impiegati.
        """

        if request.previous_plan is None:
            raise ValueError("previous_plan richiesto per il replanning")

        if request.previous_domain is None:
            raise ValueError("previous_domain richiesto quando previous_plan è presente")

        domain = request.previous_domain

        self._log(f"\n[info] [step] replanning (dominio={domain}) a partire dal piano precedente")
        await emit(on_event, EventStatus.DRAFTING, "Applicazione delle modifiche al piano esistente")
        
        draft = await self.prompts.extract_json(
            "replan.txt", 
            llm,
            domain=domain,
            question=request.question, 
            previous_plan=json.dumps(request.previous_plan, ensure_ascii=False, indent=2),
            constraints=request.constraints or "nessuno",
        )
        return await self._validate_and_correct(draft, domain, request, llm, on_event, previous_plan=request.previous_plan)
    
    # ----- fase 3: drafting -----

    async def _draft(
        self, 
        request: QueryRequest, 
        domain: PlanDomain, 
        context: dict[str, Any], 
        llm: LLMClient, 
        on_event: EventCallback | None = None
    ) -> tuple[dict[str, Any], int]:
        """
        Genera la bozza iniziale del piano delegandone la validazione logica a _validate_and_correct.

        Args:
            request (QueryRequest): La richiesta dell'utente.
            domain (PlanDomain): Il dominio del piano.
            context (dict[str, Any]): Il contesto esterno recuperato.
            llm (LLMClient): Client LLM.
            on_event (EventCallback | None): Callback SSE.

        Returns:
            tuple[dict[str, Any], int]: La bozza finale corretta e il numero di tentativi spesi.
        """
        self._log(f"\n[info] [step] drafting piano (dominio={domain})")
        await emit(on_event, EventStatus.DRAFTING, "Generazione del piano in corso")
        
        draft = await self.prompts.extract_json(
            f"draft_{domain}.txt", 
            llm,
            question=request.question,
            context=json.dumps(context, ensure_ascii=False, indent=2),
            constraints=request.constraints or "nessuno",
        )
        return await self._validate_and_correct(draft, domain, request, llm, on_event)

    async def _validate_and_correct(
        self, 
        draft: dict[str, Any] | None, 
        domain: str, 
        request: QueryRequest, 
        llm: LLMClient, 
        on_event: EventCallback | None = None, 
        previous_plan: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], int]:
        """
        Ciclo di validazione e correzione condiviso per bozze generate o aggiornate.
        In caso di fallimento della validazione logica, re-interroga LLM per il fixing.

        Args:
            draft (dict[str, Any] | None): La bozza da validare.
            domain (str): Il dominio.
            request (QueryRequest): La richiesta originaria.
            llm (LLMClient): Il client LLM.
            on_event (EventCallback | None): Callback SSE.
            previous_plan (dict[str, Any] | None): Il piano preesistente (se in fase di replan).

        Returns:
            tuple[dict[str, Any], int]: Il piano valido e il numero di tentativi impiegati.
        """
        await emit(on_event, EventStatus.VALIDATING, "Verifica della struttura del piano")
        errors = validate_draft(draft, domain, previous_plan)
        attempt = 0

        while errors and attempt < settings.max_draft_retries:
            attempt += 1
            self._log(
                f"  [warn] draft non conforme (tentativo correzione {attempt}/{settings.max_draft_retries}): {errors}",
                level=logging.WARNING
            )
            await emit(on_event, EventStatus.CORRECTING, f"Correzione del piano (tentativo {attempt}/{settings.max_draft_retries})", attempt=attempt, errors=errors)
            
            draft = await self.prompts.extract_json(
                "correct_draft.txt", 
                llm,
                question=request.question,
                errors="; ".join(errors),
                broken_json=json.dumps(draft, ensure_ascii=False) if draft else "null",
            )
            errors = validate_draft(draft, domain, previous_plan)

        if errors:
            if previous_plan is not None:
                self._log(
                    f"  [warn] replanning fallito dopo {attempt} correzioni, mantengo il piano precedente. Errori residui: {errors}",
                    level=logging.WARNING
                )
                fallback: dict[str, Any] = dict(previous_plan)
                fallback["contingency_notes"] = list(fallback.get("contingency_notes") or []) + [REPLAN_FAILURE_NOTE]
                return fallback, attempt
            
            self._log(
                f"  [warn] drafting fallito dopo {attempt} correzioni, restituisco struttura vuota. Errori residui: {errors}",
                level=logging.WARNING
            )
            return {"title": request.question, "days": []}, attempt

        self._log(f"  -> draft valido{f' dopo {attempt} correzioni' if attempt else ' al primo tentativo'}")
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
        Crea l'oggetto QueryResponse validato da Pydantic, includendo il calcolo 
        euristico della confidence in base al numero di tentativi e fallback gestiti.

        Args:
            request (QueryRequest): Richiesta utente.
            domain (PlanDomain): Dominio elaborato.
            draft (dict[str, Any]): Bozza corretta generata.
            elapsed_ms (float): Esecuzione totale.
            draft_attempts (int): Tentativi iterati per la validazione.
            context (dict[str, Any]): Contesto da servizi esterni.
            context_errors (list[str]): Errori registrati su API esterne.
            trace (list[dict[str, Any]] | None): Traccia ReAct.
            replanned (bool): Se l'esito deriva da un replan.

        Returns:
            QueryResponse: La risposta API strutturata.
        """
        try:
            days: list[PlanDay] = [PlanDay(**d) for d in draft.get("days", [])]
        except ValidationError as err:
            self._log(
                f"  [warn] validazione pydantic fallita in finalize nonostante il validatore logico: {err}",
                level=logging.WARNING
            )
            days = []

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
            context_errors=context_errors or None,
            tool_calls=trace,
            replanned=replanned,
        )

    def _out_of_scope_response(self, request: QueryRequest, elapsed_ms: float) -> QueryResponse:
        """Restituisce un wrapper standard vuoto per domande non attinenti al task del planner."""
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

    async def run(self, request: QueryRequest, on_event: EventCallback | None = None) -> QueryResponse:
        """
        Esegue l'intera pipeline dell'agente: gestisce replanning piani esistenti,
        recupero di contesto via determinismo/ReAct e la generazione iterativa di nuovi piani.

        Args:
            request (QueryRequest): I dati di input forniti all'API.
            on_event (EventCallback | None): Handler eventi per il server sent events.

        Returns:
            QueryResponse: L'output validato pronto per essere inoltrato al client.
        """
        start_time: float = time.time()
        llm = LLMClient(verbose=self.verbose, provider=request.llm_model) if request.llm_model else self.llm
        await emit(on_event, EventStatus.STARTED, "Richiesta ricevuta")

        # Gestione Replanning
        if request.previous_plan is not None:
            if request.previous_domain is None:
                raise ValueError("previous_domain è obbligatorio quando previous_plan è presente")

            draft, draft_attempts = await self._replan(request, llm, on_event)

            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            await emit(on_event, EventStatus.FINALIZING, "Composizione della risposta")

            response = self._finalize(
                request, request.previous_domain, draft, elapsed_ms, draft_attempts,
                context={}, context_errors=[], trace=None, replanned=True,
            )

            await emit(on_event, EventStatus.COMPLETED, "Piano aggiornato", confidence=response.confidence)

            return response

        # Classificazione e Gestione Nuovi Piani
        domain = await self._classify_domain(request, llm, on_event)
        if domain == "unknown":
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            response = self._out_of_scope_response(request, elapsed_ms)
            await emit(on_event, EventStatus.COMPLETED, "Richiesta fuori scope, nessun piano generato", confidence=0.0)
            return response

        # Recupero del Contesto Esterno (tramite ContextGatherer unificato)
        context_mode = request.context_mode or settings.context_gathering_mode
        context: dict[str, Any]
        context_errors: list[str]
        trace: list[dict[str, Any]] | None = None

        if context_mode == "none":
            self._log("\n[info] [step] recupero contesto esterno disattivato (context_mode='none')")
            context, context_errors = dict(request.context or {}), []
        elif context_mode == "react":
            context, context_errors, trace = await self.context_gatherer.gather_react(domain, request, llm, on_event)  # type: ignore
        else:
            context, context_errors = await self.context_gatherer.gather_deterministic(domain, request, llm, on_event)  # type: ignore

        # Generazione della Bozza
        draft, draft_attempts = await self._draft(request, domain, context, llm, on_event) # type: ignore
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        
        await emit(on_event, EventStatus.FINALIZING, "Composizione della risposta")
        response = self._finalize(
            request, domain, draft, elapsed_ms, draft_attempts,  # type: ignore
            context, context_errors, trace
        )
            
        await emit(on_event, EventStatus.COMPLETED, "Piano generato", confidence=response.confidence)
        
        return response