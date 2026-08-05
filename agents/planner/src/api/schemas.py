"""
Schema Pydantic per l'agente Planner.
"""

from datetime import date as date_
from typing import Any, Literal

from pydantic import BaseModel, Field

# domini supportati dal planner
PlanDomain = Literal["study", "travel", "routine"]


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
            "(es. entità dal KG, meteo/orari dal Multi-API). Placeholder per la futura "
            "fase di enrichment; ignorato se assente."
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
    external_data: dict[str, Any] | None = Field(
        default=None,
        description="placeholder per dati esterni arricchiti in fase di enrichment (es. meteo per itinerari di viaggio)",
    )


class QueryResponse(BaseModel):
    """risposta strutturata del planner-agent, formato unificato per i 3 domini."""

    question: str
    domain: PlanDomain
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