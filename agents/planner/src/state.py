"""
Stato in-memory dei piani generati, usato dal replanning (vedi pipeline.py:
PlannerPipeline._classify_intent / _replan / run).

Nota: stato per-processo, non condiviso tra worker/repliche e perso al riavvio - coerente
col perimetro attuale (singolo processo). Se il planner-agent verrà distribuito su più
repliche andrà sostituito con uno store esterno (Redis/DB), mantenendo la stessa interfaccia
(get/save), senza toccare pipeline.py.
"""

from dataclasses import dataclass
from typing import Any

from api.schemas import PlanDomain


@dataclass
class StoredPlan:
    """ultimo piano valido per una sessione: dominio + draft grezzo (stessa shape
    title/summary/days[]/contingency_notes usata da _draft/validate_draft), non il
    QueryResponse già finalizzato - così _replan può reiniettarlo in un prompt LLM."""

    domain: PlanDomain
    question: str
    draft: dict[str, Any]


class PlanStateStore:
    """Store in-memory dei piani per session_id: un solo piano attivo per sessione (una
    nuova richiesta 'new_plan' sulla stessa sessione sovrascrive il piano precedente).
    Nessuna scadenza/TTL per ora - nota per la roadmap, non un bug."""

    def __init__(self) -> None:
        self._plans: dict[str, StoredPlan] = {}

    def get(self, session_id: str | None) -> StoredPlan | None:
        if session_id is None:
            return None
        return self._plans.get(session_id)

    def save(self, session_id: str | None, domain: PlanDomain, question: str, draft: dict[str, Any]) -> None:
        if session_id is None:
            return
        self._plans[session_id] = StoredPlan(domain=domain, question=question, draft=draft)


# istanza singola condivisa dal processo, stesso pattern di `settings = Settings()` in configs/settings.py
plan_state_store = PlanStateStore()