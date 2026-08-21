"""
Schema Pydantic per l'agente Planner    .
"""

from datetime import date as date_
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- DOMAIN DEFINITIONS --- 

# Verrà iniettato dinamicamente nel prompt di classificazione.
DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "study": "study plans, exam preparation, course schedules, learning goals.",
    "travel": "travel itineraries, trips, visits to places, vacation planning.",
    "routine": "daily/weekly routines, habits, recurring personal schedules not tied to study or travel."
}

# Domini supportati dal planner (usato anche per domain_hint)
PlanDomain = Literal["study", "travel", "routine"]

# Dominio effettivo restituito in output (incluso l'out-of-scope)
ResponseDomain = PlanDomain | Literal["unknown"]


# INPUT

class QueryRequest(BaseModel):
    """richiesta in ingresso al planner-agent."""

    question: str = Field(
        ...,
        description="richiesta in linguaggio naturale da scomporre in un piano",
        json_schema_extra={
            "examples": ["Devo preparare l'esame di Reti in 3 settimane, studio 2 ore al giorno nei feriali"]
        },
    )
    domain_hint: PlanDomain | None = Field(
        default=None,
        description=(
            "override manuale del dominio (bypassa la classificazione interna); "
            "utile se il supervisor lo ha già determinato a monte"
        ),
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "contesto opzionale precompilato da altri agenti dell'orchestratore "
            "(es. entità dal KG, meteo/orari dal Multi-API). Usato come base di partenza "
            "da _gather_context; ignorato se assente."
        ),
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "identificativo di sessione/conversazione. Se presente e nello stato è già "
            "salvato un piano per questo id, la richiesta viene classificata come "
            "'new_plan' oppure 'replan' (modifica del piano esistente, vedi "
            "PlannerPipeline._classify_intent); un 'replan' aggiorna il piano invece di "
            "generarne uno da zero. Se assente, il comportamento è quello storico: nessuno "
            "stato viene letto o salvato."
        ),
    )


# OUTPUT

class TimeSlot(BaseModel):
    """unità minima di time-boxing: un'attività allocata in un intervallo di tempo."""

    task: str = Field(..., description="attività da svolgere in questo slot")
    start_time: str | None = Field(
        default=None,
        description="orario di inizio in formato HH:MM; None se lo slot non è ancorato a un orario preciso (es. 'mattina')",
    )
    duration_minutes: int = Field(..., gt=0, description="durata dell'attività in minuti")
    category: str | None = Field(
        default=None,
        description="etichetta libera per il tipo di attività (es. 'studio', 'trasporto', 'pasto', 'riposo')",
    )
    subtasks: list[str] | None = Field(
        default=None,
        description="scomposizione opzionale dell'attività in sotto-task più granulari",
    )
    notes: str | None = None


class PlanDay(BaseModel):
    """un giorno del piano, contenente gli slot temporali allocati."""

    day_index: int = Field(..., ge=1, description="numero progressivo del giorno nel piano, a partire da 1")
    date: date_ | None = Field(
        default=None,
        description=(
            "data reale se applicabile (es. itinerari di viaggio); "
            "None per piani relativi (es. 'Giorno 3' di un piano di studio)"
        ),
    )
    label: str | None = Field(
        default=None, description="etichetta descrittiva del giorno (es. 'Arrivo a Roma', 'Ripasso capitoli 1-3')"
    )
    slots: list[TimeSlot] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """risposta strutturata del planner-agent, formato unificato per i 3 domini."""

    question: str
    domain: ResponseDomain
    title: str = Field(..., description="titolo sintetico del piano generato")
    summary: str | None = Field(
        default=None, description="riassunto discorsivo del piano, utile al synthesizer dell'orchestratore"
    )
    days: list[PlanDay]
    contingency_notes: list[str] | None = Field(
        default=None,
        description="piani B / alternative, secondari rispetto alla scomposizione principale",
    )
    confidence: float = 1.0
    execution_time_ms: float | None = None
    gathered_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "risposte grezze recuperate da kg-agent/multiapi-agent (dominio 'travel'), sotto le "
            "chiavi 'kg_agent'/'multiapi_agent'. Ogni chiave contiene una lista di risposte grezze "
            "(un solo elemento in modalità 'deterministic', uno o più in modalità 'react' se lo "
            "stesso tool viene richiamato più volte nello stesso loop), più l'eventuale "
            "request.context di partenza riportato così com'è. None se non è stato "
            "recuperato/fornito alcun contesto."
        )
    )
    context_errors: list[str] | None = Field(
        default=None,
        description=(
            "errori di rete/timeout registrati durante il recupero del contesto esterno "
            "(kg-agent/multiapi-agent). Sono anche riportati in contingency_notes per l'utente "
            "finale; qui restano isolati per introspezione/benchmark. None se non è stato "
            "tentato alcun recupero di contesto o non ci sono stati errori."
        )
    )
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None,
        description="Traccia del loop ReAct: contiene i thought, le azioni scelte e le osservazioni."
    )
    replanned: bool = Field(
        default=False,
        description=(
            "True se questa risposta è un aggiornamento di un piano esistente (replanning) "
            "invece di un piano generato da zero."
        ),
    )