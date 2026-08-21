"""
Gestione dello stato in-memory per i piani generati.

Fornisce le strutture dati e lo store (per-processo) necessari per il replanning.
Nota architetturale: lo stato è limitato al singolo processo e si azzera al riavvio.
Se il microservizio verrà scalato su più repliche, questo modulo fungerà da
interfaccia (facciata) per uno storage esterno (es. Redis o DB), lasciando
intatta la pipeline.
"""

from dataclasses import dataclass
from typing import Any

from api.schemas import PlanDomain


@dataclass
class StoredPlan:
    """
    Rappresenta l'ultimo piano valido generato per una specifica sessione.
    
    Conserva il dominio originario, la domanda posta dall'utente e il 
    draft grezzo del piano (ovvero il JSON restituito dal LLM e validato).
    Il draft viene salvato crudo e non come QueryResponse per poter 
    essere re-iniettato agevolmente nel prompt in caso di replanning.
    """
    domain: PlanDomain
    question: str
    draft: dict[str, Any]


class PlanStateStore:
    """
    Store in-memory (chiave-valore) per i piani attivi.
    Associa ogni session_id all'ultimo StoredPlan generato.
    """

    def __init__(self) -> None:
        """Inizializza il dizionario interno vuoto per i piani."""
        self._plans: dict[str, StoredPlan] = {}

    def get(self, session_id: str | None) -> StoredPlan | None:
        """
        Recupera un piano salvato per un determinato ID di sessione.

        Args:
            session_id (str | None): L'identificativo della sessione.

        Returns:
            StoredPlan | None: Il piano memorizzato, oppure None se l'ID 
            è assente o non valido.
        """
        if session_id is None:
            return None
        return self._plans.get(session_id)

    def save(
        self, 
        session_id: str | None, 
        domain: PlanDomain, 
        question: str, 
        draft: dict[str, Any]
    ) -> None:
        """
        Salva o sovrascrive un piano per l'ID di sessione specificato.

        Args:
            session_id (str | None): L'identificativo della sessione. Se None, 
                                     il salvataggio viene ignorato.
            domain (PlanDomain): Il dominio del piano.
            question (str): La richiesta dell'utente.
            draft (dict[str, Any]): Il JSON del piano generato e validato.
        """
        if session_id is None:
            return
        
        self._plans[session_id] = StoredPlan(
            domain=domain, 
            question=question, 
            draft=draft
        )


# Istanza singola condivisa dal processo (Singleton pattern rudimentale).
plan_state_store: PlanStateStore = PlanStateStore()