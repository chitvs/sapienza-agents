from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

class KnowledgeGraphUnavailableError(Exception):
    """Il knowledge graph non è raggiungibile o non ha risposto."""

    def __init__(self, kg: str, detail: str) -> None:
        super().__init__(f"{kg} non raggiungibile: {detail}")
        self.kg = kg
        self.detail = detail

@dataclass
class EntityReference:
    """Riferimento ad un'altra entità."""
    id: str
    label: str | None = None

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

    # Convenzioni di citazione del KG ("wd:"/"wdt:" su Wikidata, nessun prefisso su
    # Neo4j). Vivono qui perché i pruner riusabili possano formattare il contesto
    # senza sapere con quale KG stanno lavorando.
    entity_prefix: str = ""
    property_prefix: str = ""

    @abstractmethod
    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """Cerca entità a partire dal testo di una menzione."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> EntityData:
        """Recupera i dati completi di un'entità dal suo id."""
        raise NotImplementedError

    @abstractmethod
    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Risolve id e URI grezzi in etichette leggibili."""
        raise NotImplementedError

    def format_entity_ref(self, entity_id: str) -> str:
        """Compone il riferimento con cui citare l'entità dentro una query."""
        # id dei kg che contengono caratteri non ammessi nei nomi prefissati SPARQL
        # (es. DBpedia con "Mercury_(planet)") sovrascrivono questo metodo
        return f"{self.entity_prefix}{entity_id}"

    def looks_like_entity_id(self, value: str) -> bool:
        """Indica se un valore è un riferimento a un'altra entità anziché un letterale."""
        # default conservativo: senza override nessun valore viene risolto per errore
        return False

    def is_valid_candidate(self, candidate: EntityCandidate) -> bool:
        """Indica se un candidato di search_entity è utilizzabile per la disambiguazione."""
        # sapere quali voci sono spazzatura (es. le pagine di disambiguazione Wikidata)
        # è conoscenza del KG, quindi sta qui e non nel linker, che resta agnostico
        return bool(getattr(candidate, "id", ""))
