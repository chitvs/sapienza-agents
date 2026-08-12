from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# classe di eccezione custom
class KnowledgeGraphUnavailableError(Exception):
    """Il knowledge graph non è raggiungibile o non ha risposto."""

    def __init__(self, kg: str, detail: str) -> None:
        super().__init__(f"{kg} non raggiungibile: {detail}")
        self.kg = kg
        self.detail = detail

# strutture dati per le entità
@dataclass
class EntityCandidate:
    id: str
    label: str
    description: str | None = None

@dataclass
class EntityData:
    id: str
    label: str
    properties: dict[str, list[str]]
    description: str = ""

class BaseConnector(ABC):
    """Interfaccia verso un knowledge graph."""

    # convenzioni di citazione del KG ("wd:"/"wdt:" su Wikidata)
    entity_prefix: str = ""
    property_prefix: str = ""

    # limite delle cache in-memory dei connettori che ne hanno; 0 significa nessun limite
    max_cache_size: int = 0

    @abstractmethod
    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """Cerca entità a partire dal testo di una menzione."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> EntityData:
        """Recupera i dati completi di un'entità dal suo id."""
        raise NotImplementedError

    def get_entities(self, entity_ids: list[str]) -> dict[str, EntityData]:
        """Recupera più entità insieme."""
        return {eid: self.get_entity(eid) for eid in entity_ids}

    def get_schema(self) -> dict[str, Any]:
        """Restituisce lo schema del grafo."""
        return {}

    @abstractmethod
    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Risolve id e URI grezzi in etichette leggibili."""
        raise NotImplementedError

    def _set_cache_entry(self, cache_dict: dict, key: str, value: Any) -> None:
        """Memorizza un elemento rispettando il limite della cache."""
        if self.max_cache_size and len(cache_dict) >= self.max_cache_size and key not in cache_dict:
            oldest = next(iter(cache_dict), None)
            if oldest is not None:
                cache_dict.pop(oldest, None) # FIFO
        cache_dict[key] = value

    def format_entity_ref(self, entity_id: str) -> str:
        """Compone il riferimento con cui citare l'entità dentro una query."""
        return f"{self.entity_prefix}{entity_id}"

    def candidate_prominence(self, candidates: list[EntityCandidate]) -> dict[str, float]:
        """Notorietà di ciascun candidato secondo il KG; vuoto se il KG non la espone."""
        return {}

    def is_valid_candidate(self, candidate: EntityCandidate) -> bool:
        """Indica se un candidato di search_entity è utilizzabile per la disambiguazione."""
        return bool(candidate.id)
