"""
Recupero del contesto esterno per il Planner (kg-agent, multiapi-agent).

Due strategie, selezionabili per-richiesta (QueryRequest.context_mode):
- deterministica: formula (via LLM leggero) una sotto-domanda mirata per
  ciascun tool richiesto esplicitamente dall'utente tramite
  `request.allowed_tools`, poi li esegue in parallelo; il dispatch (quali/se
  chiamare) resta deciso a priori, non dall'LLM (ContextGatherer.gather_deterministic).
- ReAct: un loop di tool-calling in cui l'LLM decide dinamicamente quali
  fonti interrogare, entro TOOL_DESCRIPTIONS e settings.max_react_steps
  (ContextGatherer.gather_react).
"""

import asyncio
import json
import logging
from typing import Any

from api.schemas import PlanDomain, QueryRequest
from configs.settings import settings
from utils.events import EventCallback, EventStatus, emit, run_tracked_tool
from clients.llm_client import LLMClient
from utils.logging_utils import make_logger
from core.prompts import PromptLibrary
from core.tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY

logger = logging.getLogger("planner_context")


class ContextGatherer:
    """Recupera il contesto esterno per una richiesta, in modalità deterministica o ReAct."""

    def __init__(self, prompts: PromptLibrary, verbose: bool = False) -> None:
        """Inizializza il gatherer.

        Args:
            prompts: La libreria di prompt condivisa con PlannerPipeline (stessa
                cache in memoria, evita di ricaricare da disco gli stessi template).
            verbose: Se True, oltre al logger stampa anche a schermo i passaggi.
        """
        self.verbose = verbose
        self._log = make_logger(logger, verbose)
        self._prompts = prompts

    async def gather_deterministic(
        self, domain: PlanDomain, request: QueryRequest, llm: LLMClient, on_event: EventCallback | None = None
    ) -> tuple[dict[str, Any], list[str]]:
        """Recupera il contesto esterno in modo deterministico: esegue i tool
        specificati in input dall'utente tramite `allowed_tools`, dopo aver
        formulato per ciascuno una sotto-domanda mirata (passaggio LLM leggero,
        non un tool-calling loop: la scelta di quali/se chiamare i tool resta
        fissata da `allowed_tools`, non decisa dall'LLM).

        Args:
            domain: Il dominio del piano classificato al passo 1 (ignorato in questa modalità).
            request: La richiesta originale.
            llm: Il client LLM risolto per questa richiesta, usato solo per formulare le sotto-domande.
            on_event: Callback opzionale per gli eventi di avanzamento (streaming).

        Returns:
            Il contesto arricchito e la lista degli eventuali fallimenti di rete.
        """
        context: dict[str, Any] = dict(request.context or {})
        errors: list[str] = []

        # Se l'utente non ha richiesto esplicitamente dei tool, non eseguiamo nulla
        allowed = request.allowed_tools
        if not allowed:
            self._log("  [info] nessun tool esplicito in allowed_tools, gather deterministico saltato")
            return context, errors

        # Selezioniamo i tool richiesti verificando che esistano nel registry
        active_names = [name for name in allowed if name in TOOL_REGISTRY]
        if not active_names:
            return context, errors

        self._log(f"\n[info] [step] recupero contesto esterno deterministico ({', '.join(active_names)})")
        await emit(on_event, EventStatus.GATHERING_CONTEXT, "Recupero contesto esterno in corso")

        # Formuliamo una sotto-domanda mirata per ciascun tool attivo, ripescando
        # nome+descrizione da TOOL_DESCRIPTIONS (stessa fonte usata da gather_react):
        # niente elenco di tool hardcoded nel prompt.
        active_tools = [t for t in TOOL_DESCRIPTIONS if t["name"] in active_names]
        queries = await self._prompts.extract_json(
            "formulate_queries.txt", llm,
            question=request.question,
            tools=json.dumps(active_tools, ensure_ascii=False, indent=2),
        )
        if not isinstance(queries, dict):
            self._log(
                "  [warn] formulate_queries: risposta LLM non valida, fallback alla domanda originale per tutti i tool",
                level=logging.WARNING,
            )
            queries = {}

        # Fallback per-singolo-tool: se l'LLM omette o sbaglia la chiave di un
        # tool, quel tool riceve comunque la domanda originale invece di essere
        # saltato o rotto.
        sub_questions: dict[str, str] = {}
        for name in active_names:
            candidate = queries.get(name)
            sub_questions[name] = candidate.strip() if isinstance(candidate, str) and candidate.strip() else request.question

        # Esecuzione in parallelo dei tool richiesti, ciascuno con la propria sotto-domanda mirata
        results = await asyncio.gather(
            *(run_tracked_tool(on_event, name, TOOL_REGISTRY[name](sub_questions[name])) for name in active_names)
        )

        for name, result in zip(active_names, results):
            if "error" in result:
                errors.append(result["error"])
                self._log(f"  [warn] {name}: {result['error']}", level=logging.WARNING)
            else:
                context[name] = [result]

        return context, errors

    async def gather_react(
        self, domain: PlanDomain, request: QueryRequest, llm: LLMClient, on_event: EventCallback | None = None
    ) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
        """Recupera il contesto esterno tramite un loop di tool-calling ReAct: a
        ogni passo l'LLM decide se chiamare un tool (tra quelli ancora
        disponibili) o terminare ('finish'), fino a settings.max_react_steps passi.

        Args:
            domain: Il dominio del piano.
            request: La richiesta in ingresso.
            llm: Il client LLM risolto per questa richiesta.
            on_event: Callback opzionale per gli eventi di avanzamento (streaming).

        Returns:
            Una tripla (contesto arricchito, errori riscontrati, traccia del ragionamento).
        """
        context: dict[str, Any] = dict(request.context or {})
        errors: list[str] = []
        trace: list[dict[str, Any]] = []
        scratchpad: list[str] = []

        available_tools = [
            t for t in TOOL_DESCRIPTIONS
            if request.allowed_tools is None or t["name"] in request.allowed_tools
        ]

        if available_tools:
            await emit(on_event, EventStatus.GATHERING_CONTEXT, "Recupero contesto esterno (ReAct) in corso")

        for step in range(settings.max_react_steps):
            if not available_tools:
                self._log("  [react] nessun tool rimanente disponibile, interrompo il loop anticipatamente")
                break

            decision = await self._prompts.extract_json(
                "gather_context_react.txt", llm,
                domain=domain, question=request.question,
                scratchpad="\n".join(scratchpad) or "(vuoto)",
                tools=json.dumps(available_tools, ensure_ascii=False, indent=2),
            )

            if not decision or decision.get("action") not in ("call_tool", "finish"):
                msg = f"gather_context_react: decisione non valida al passo {step + 1} ({decision!r}), interrotto"
                self._log(f"  [warn] {msg}", level=logging.WARNING)
                errors.append(msg)
                break

            if decision["action"] == "finish":
                self._log(f"  [react] finish - {decision.get('thought', '')}")
                break

            tool_name: str | None = decision.get("tool")
            # 'or', non il default di .get(): se l'LLM restituisce esplicitamente
            # "tool_input": null dobbiamo comunque avere una domanda da inoltrare.
            tool_input: str = decision.get("tool_input") or request.question

            # Il dispatch rispetta available_tools, non solo TOOL_REGISTRY: un
            # tool già rimosso per un fallimento precedente resta non richiamabile
            # anche se l'LLM insiste a richiederlo.
            if str(tool_name) not in {t["name"] for t in available_tools}:
                obs: dict[str, Any] = {
                    "error": (
                        f"tool non più disponibile in questo step: {tool_name!r}"
                        if tool_name in TOOL_REGISTRY
                        else f"tool sconosciuto: {tool_name!r}"
                    )
                }
            else:
                obs = await run_tracked_tool(on_event, str(tool_name), TOOL_REGISTRY[str(tool_name)](tool_input))

            trace.append({
                "step": step + 1,
                "thought": decision.get("thought", ""),
                "tool": tool_name,
                "tool_input": tool_input,
                "observation": obs,
            })

            if "error" in obs:
                errors.append(obs["error"])
                available_tools = [t for t in available_tools if t["name"] != tool_name]
                self._log(f"  [react] tool '{tool_name}' fallito e rimosso dalla lista per i prossimi step")
            else:
                context.setdefault(str(tool_name), []).append(obs)

            scratchpad.append(
                f"Thought: {decision.get('thought', '')}\n"
                f"Action: {tool_name}({tool_input})\n"
                f"Observation: {json.dumps(obs, ensure_ascii=False)}"
            )
        else:
            # Raggiunto il limite di iterazioni senza un 'finish' esplicito.
            msg = f"gather_context_react: raggiunto max_react_steps={settings.max_react_steps} senza 'finish'"
            self._log(f"  [warn] {msg}", level=logging.WARNING)
            errors.append(msg)

        return context, errors, trace