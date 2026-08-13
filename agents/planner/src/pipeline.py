import asyncio
import json
import logging
import re
import time

import httpx
from pydantic import ValidationError
from typing import Literal

from api.schemas import PlanDay, PlanDomain, QueryRequest, QueryResponse, ResponseDomain
from configs.settings import settings
from state import plan_state_store, StoredPlan
from tools import query_kg, query_multiapi, TOOL_REGISTRY, TOOL_DESCRIPTIONS
from validators import validate_draft


logger = logging.getLogger("planner_pipeline")

# mapping dominio -> prompt di drafting specializzato (punto 3 della roadmap)
_DRAFT_PROMPTS: dict[str, str] = {
    "study": "draft_study.txt",
    "travel": "draft_travel.txt",
    "routine": "draft_routine.txt",
}


class PlannerPipeline:
    """pipeline dell'agente planner: classifica il dominio, recupera contesto esterno
    (deterministico per 'study'/'routine', oppure via ReAct per 'travel' quando
    settings.context_gathering_mode == "react"), genera una bozza del piano e finalizza
    la risposta.

    Fasi: classify_domain -> gather_context (deterministic o react) -> draft -> finalize
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._prompts_cache: dict[str, str] = {}

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    # -- llm helpers (stesso pattern di multiapi, self-contained) ----

    async def _llm_generate(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """Prova il provider configurato; se è gemini e fallisce, ripiega su ollama."""
        if settings.llm_provider.lower() == "gemini":
            try:
                return await self._generate_gemini(prompt, temperature, json_mode)
            except Exception as err:
                self._log(f"  [warn] gemini non disponibile ({err.__class__.__name__}: {err}), fallback su ollama")
                return await self._generate_ollama(prompt, temperature, json_mode)
        return await self._generate_ollama(prompt, temperature, json_mode)

    async def _generate_gemini(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY non configurata")

        url = f"{settings.gemini_api_base}/models/{settings.gemini_model}:generateContent"
        headers = {"x-goog-api-key": settings.gemini_api_key}

        generation_config: dict = {}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        # temperature/top_p/top_k deprecati e ignorati da gemini-3.6-flash in poi
        # (Google: verranno rifiutati con HTTP 400 nelle prossime generazioni) - non inviati.

        payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if generation_config:
            payload["generationConfig"] = generation_config

        async with httpx.AsyncClient(timeout=settings.gemini_timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                block_reason = data.get("promptFeedback", {}).get("blockReason")
                self._log(f"  [warn] gemini: nessuna candidate, blockReason={block_reason!r}")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "").strip() if parts else ""

    async def _generate_ollama(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """Chiama Ollama locale via HTTP REST."""
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    
    @staticmethod
    def _clean_json(raw: str) -> str:
        """rimuove eventuali blocchi markdown (```json ... ```) dalla risposta llm."""
        if not raw:
            return ""
        cleaned = raw.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return cleaned

    def _load_prompt(self, filename: str) -> str:
        """carica un template prompt dalla cartella prompts (con cache)."""
        if filename not in self._prompts_cache:
            path = settings.prompts_dir / filename
            self._prompts_cache[filename] = path.read_text(encoding="utf-8")
        return self._prompts_cache[filename]

    async def _llm_extract_json(self, prompt_file: str, **format_kwargs) -> dict | None:
        """helper generico: carica un prompt, lo invia al llm, parsa il json di risposta."""
        template = self._load_prompt(prompt_file)
        prompt = template.format(**format_kwargs)
        raw = await self._llm_generate(prompt, json_mode=True)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log(f"  [warn] impossibile parsare json: {cleaned}")
            return None

    # ----- fase 1: classificazione del dominio -----

    async def _classify_domain(self, request: QueryRequest) -> ResponseDomain:
        if request.domain_hint is not None:
            self._log(f"[info] dominio forzato da domain_hint: {request.domain_hint}")
            return request.domain_hint

        self._log("\n[info] [step] classificazione dominio via llm")
        data = await self._llm_extract_json("classify_domain.txt", question=request.question)

        domain = data.get("domain") if data else None
        if domain in ("study", "travel", "routine"):
            self._log(f"  -> dominio classificato: {domain}")
            return domain

        # sia il caso esplicito 'unknown' del modello sia un fallimento di classificazione
        # (json malformato, campo mancante, valore non riconosciuto) finiscono qui: MAI un
        # fallback silenzioso su un dominio a caso, che forzerebbe il drafting a inventare
        # un piano di studio/viaggio/routine per una domanda che non c'entra nulla.
        self._log(f"  [warn] dominio non riconosciuto o fuori scope ({domain!r}), classificato come 'unknown'")
        return "unknown"

    # ----- fase 2: recupero contesto esterno (deterministico, per dominio) -----

    async def _gather_context(self, domain: PlanDomain, request: QueryRequest) -> tuple[dict, list[str]]:
        """recupera contesto esterno in modo deterministico in base al dominio già
        classificato: zero chiamate LLM per decidere quali tool usare (nessun tool-calling
        dinamico).

        Restituisce (context, errors): errors è una lista di descrizioni di fallimento,
        non un semplice bool/flag generico - stesso principio già in uso in validators.py -
        così ogni voce può essere appesa direttamente a contingency_notes senza sintesi
        intermedia.
        """
        context: dict = {}
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
                    self._log(f"  [warn] {key}: {result['error']}")
                else:
                    # lista per coerenza di shape con _gather_context_react (che può
                    # accumulare più risposte per lo stesso tool): qui sarà sempre un
                    # solo elemento, ma il consumer a valle (synthesizer/orchestrator)
                    # non deve dover distinguere le due modalità.
                    # sovrascrive eventuali chiavi in conflitto già presenti da request.context
                    context[key] = [result]
        # domain in ("study", "routine"): pass-through esplicito, nessuna chiamata di rete.
        # 'study' non fa pre-calcolo (vedi nota "paradosso study" nella roadmap): i parametri
        # necessari (settimane disponibili, giorni esclusi, budget orario) esistono solo nel
        # testo libero della domanda. 'routine' non ha bisogno di dati esterni per definizione.

        return context, errors


    async def _gather_context_react(self, domain: PlanDomain, request: QueryRequest) -> tuple[dict, list[str], list[dict]]:
        context: dict = dict(request.context or {})
        errors: list[str] = []
        trace: list[dict] = []
        scratchpad: list[str] = []

        for step in range(settings.max_react_steps):
            decision = await self._llm_extract_json(
                "gather_context_react.txt",
                domain=domain, 
                question=request.question,
                scratchpad="\n".join(scratchpad) or "(vuoto)",
                tools=json.dumps(TOOL_DESCRIPTIONS, ensure_ascii=False, indent=2) # <-- NUOVO
            )
            
            if not decision or decision.get("action") not in ("call_tool", "finish"):
                msg = f"gather_context_react: decisione non valida al passo {step + 1} ({decision!r}), interrotto"
                self._log(f"  [warn] {msg}")
                errors.append(msg)
                break
            if decision["action"] == "finish":
                self._log(f"  [react] finish - {decision.get('thought', '')}")
                break

            tool_name = decision.get("tool")
            # 'or' e non .get(key, default): un LLM può restituire "tool_input": null
            # esplicito, che .get(..., default) non intercetterebbe
            tool_input = decision.get("tool_input") or request.question
            tool_fn = TOOL_REGISTRY.get(tool_name)
            obs = {"error": f"tool sconosciuto: {tool_name!r}"} if tool_fn is None else await tool_fn(tool_input)

            trace.append({"step": step + 1, "thought": decision.get("thought", ""),
                        "tool": tool_name, "tool_input": tool_input, "observation": obs})
            if "error" in obs:
                errors.append(obs["error"])
            else:
                context.setdefault(tool_name, []).append(obs)  # lista: il tool può essere richiamato più volte
            scratchpad.append(f"Thought: {decision.get('thought','')}\nAction: {tool_name}({tool_input})\nObservation: {json.dumps(obs, ensure_ascii=False)}")
        else:
            msg = f"gather_context_react: raggiunto max_react_steps={settings.max_react_steps} senza 'finish'"
            self._log(f"  [warn] {msg}")
            errors.append(msg)

        return context, errors, trace

    # ----- fase 3: drafting -----

    async def _draft(self, request: QueryRequest, domain: PlanDomain, context: dict) -> tuple[dict, int]:
        """genera la bozza del piano via llm, con prompt specializzato per dominio. [...]
        La validazione/correzione della bozza è delegata a `_validate_and_correct`,
        condivisa con `_replan` (stesso ciclo, prompt di partenza diverso).
        """
        self._log(f"\n[info] [step] drafting piano (dominio={domain})")
        draft = await self._llm_extract_json(
            _DRAFT_PROMPTS[domain],
            question=request.question,
            context=json.dumps(context, ensure_ascii=False, indent=2),
        )
        return await self._validate_and_correct(draft, domain, request)

    async def _validate_and_correct(self, draft: dict | None, domain: PlanDomain, request: QueryRequest) -> tuple[dict, int]:
        """ciclo di validazione/correzione condiviso da `_draft` e `_replan` (contenuto
        identico al vecchio corpo di `_draft` dopo la generazione della bozza iniziale)."""
        errors = validate_draft(draft, domain)

        attempt = 0
        while errors and attempt < settings.max_draft_retries:
            attempt += 1
            self._log(f"  [warn] draft non conforme (tentativo correzione {attempt}/{settings.max_draft_retries}): {errors}")
            draft = await self._llm_extract_json(
                "correct_draft.txt",
                question=request.question,
                errors="; ".join(errors),
                broken_json=json.dumps(draft, ensure_ascii=False) if draft else "null",
            )
            errors = validate_draft(draft, domain)

        if errors:
            self._log(f"  [warn] drafting fallito dopo {attempt} correzioni, restituisco struttura vuota. Errori residui: {errors}")
            return {"title": request.question, "days": []}, attempt

        self._log(f"  -> draft valido{f' dopo {attempt} correzioni' if attempt else ' al primo tentativo'}")
        return draft, attempt
    
    # ----- fase 2.5: replanning (modifica di un piano esistente, invece di generarne uno nuovo) -----

    async def _classify_intent(self, request: QueryRequest, stored: StoredPlan) -> Literal["new_plan", "replan"]:
        """invocato solo se esiste già un piano salvato per request.session_id: decide se
        il messaggio è una richiesta di piano nuovo o una modifica del piano esistente.

        Stesso principio di 'mai un fallback silenzioso su un valore a caso' già seguito in
        _classify_domain: qui però un fallback è accettabile, perché il caso peggiore
        (classificazione fallita) è ricadere sul comportamento storico 'new_plan', non
        inventare una modifica non richiesta a un piano esistente.
        """
        self._log("\n[info] [step] classificazione intento (nuovo piano vs replanning)")
        data = await self._llm_extract_json(
            "classify_intent.txt",
            question=request.question,
            domain=stored.domain,
            existing_title=stored.draft.get("title", ""),
        )
        intent = data.get("intent") if data else None
        if intent in ("new_plan", "replan"):
            self._log(f"  -> intento classificato: {intent}")
            return intent
        self._log(f"  [warn] intento non riconosciuto ({intent!r}), fallback su 'new_plan'")
        return "new_plan"

    async def _replan(self, request: QueryRequest, stored: StoredPlan) -> tuple[dict, int]:
        """genera una bozza aggiornata a partire dal piano salvato in stato, invece che da
        zero: stesso ciclo di validazione/correzione di _draft (_validate_and_correct), ma
        il prompt riceve il piano precedente al posto del contesto esterno.
        """
        self._log(f"\n[info] [step] replanning (dominio={stored.domain}) a partire dallo stato salvato")
        draft = await self._llm_extract_json(
            "replan.txt",
            question=request.question,
            domain=stored.domain,
            previous_plan=json.dumps(stored.draft, ensure_ascii=False, indent=2),
        )
        return await self._validate_and_correct(draft, stored.domain, request)

    # ----- fase 4: finalizzazione -----

    def _finalize(
        self,
        request: QueryRequest,
        domain: PlanDomain,
        draft: dict,
        elapsed_ms: float,
        draft_attempts: int,
        context: dict,
        context_errors: list[str],
        trace: list[dict] | None = None,
        replanned: bool = False,
    ) -> QueryResponse:
        try:
            days = [PlanDay(**d) for d in draft.get("days", [])]
        except ValidationError as err:
            # rete di sicurezza: il validatore logico opera sul dict grezzo e non copre
            # ogni possibile disallineamento di tipo con lo schema Pydantic; se succede
            # comunque, non far esplodere la richiesta con un 500, restituisci un piano
            # vuoto a bassa confidence (coerente con un drafting fallito).
            self._log(f"  [warn] validazione pydantic fallita in finalize nonostante il validatore logico: {err}")
            days = []

        # ogni fallimento di _gather_context resta descritto singolarmente (non una riga
        # sintetica unica), appeso alle eventuali contingency_notes già presenti nel draft.
        contingency_notes = list(draft.get("contingency_notes") or [])
        contingency_notes.extend(context_errors)

        if not days:
            confidence = 0.0
        else:
            confidence = 1.0 - settings.confidence_retry_penalty * draft_attempts
            if context_errors:
                confidence -= settings.confidence_context_error_penalty
            confidence = round(max(settings.confidence_floor, confidence), 2)

        return QueryResponse(
            question=request.question,
            domain=domain,
            title=draft.get("title") or request.question,
            summary=draft.get("summary"),
            days=days,
            contingency_notes=contingency_notes or None,
            confidence=confidence,
            execution_time_ms=elapsed_ms,
            gathered_context=context or None,
            tool_calls=trace,
        )

    # ----- risposta esplicita per richieste fuori scope -----

    def _out_of_scope_response(self, request: QueryRequest, elapsed_ms: float) -> QueryResponse:
        """risposta quando la richiesta non rientra in nessuno dei domini gestiti dal planner.

        Evita di forzare la domanda in un dominio a caso (che produrrebbe un drafting
        insensato/allucinato) e di sollevare un errore HTTP per un caso che non è un guasto
        tecnico: stesso principio già adottato da multiapi-agent per gli intent non
        supportati (200 con un payload che segnala esplicitamente il problema, lasciando al
        synthesizer dell'orchestratore il compito di formulare una risposta discorsiva).
        """
        self._log("  [warn] richiesta fuori scope per il planner, nessun drafting eseguito")
        return QueryResponse(
            question=request.question,
            domain="unknown",
            title=request.question,
            summary=(
                "Questa richiesta non riguarda pianificazione di studio, itinerari di viaggio o "
                "routine giornaliere: il planner-agent non genera un piano per questo tipo di domanda."
            ),
            days=[],
            contingency_notes=None,
            confidence=0.0,
            execution_time_ms=elapsed_ms,
        )

    # ----- entrypoint pubblico -----

    async def run(self, request: QueryRequest) -> QueryResponse:
            start_time = time.time()

            # --- REPLANNING: solo se esiste già un piano salvato per questa sessione ---
            stored = plan_state_store.get(request.session_id)
            if stored is not None:
                intent = await self._classify_intent(request, stored)
                if intent == "replan":
                    draft, draft_attempts = await self._replan(request, stored)
                    elapsed_ms = round((time.time() - start_time) * 1000, 2)
                    response = self._finalize(
                        request, stored.domain, draft, elapsed_ms, draft_attempts,
                        context={}, context_errors=[], trace=None, replanned=True,
                    )
                    if draft.get("days"):
                        plan_state_store.save(request.session_id, stored.domain, request.question, draft)
                    return response
                # intent == "new_plan": si prosegue con la generazione da zero qui sotto,
                # che sovrascriverà il piano salvato in stato a fine funzione.

            domain = await self._classify_domain(request)
            if domain == "unknown":
                elapsed_ms = round((time.time() - start_time) * 1000, 2)
                return self._out_of_scope_response(request, elapsed_ms)

            # --- LOGICA DI BIFORCAZIONE ---
            if settings.context_gathering_mode == "react" and domain == "travel":
                context, context_errors, trace = await self._gather_context_react(domain, request)
            else:
                context, context_errors = await self._gather_context(domain, request)
                trace = None

            draft, draft_attempts = await self._draft(request, domain, context)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            response = self._finalize(request, domain, draft, elapsed_ms, draft_attempts, context, context_errors, trace)
            if draft.get("days"):
                plan_state_store.save(request.session_id, domain, request.question, draft)
            return response