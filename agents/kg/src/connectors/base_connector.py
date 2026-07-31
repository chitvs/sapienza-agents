from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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

    @abstractmethod
    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """cerca entità a partire da testo, ritorna una lista di entità candidate."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> EntityData:
        """recupera i dati completi di un'entità nota dal suo id."""
        raise NotImplementedError

    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        risolve gli uri/id grezzi restituendo etichette leggibili in linguaggio naturale.
        di default esamina ciascuna chiave/valore e converte gli uri conosciuti tramite get_entity().
        """
        grounded_results = []
        resolved: dict[str, str] = {}
        for row in raw_results:
            grounded_row = {}
            for var_name, var_data in row.items():
                if isinstance(var_data, dict):
                    val = var_data.get("value", "")
                else:
                    val = str(var_data)

                # se il valore è un URI di risorsa/entità (es. wikidata QID o DBpedia resource URI)
                if "wikidata.org/entity/Q" in val or "dbpedia.org/resource/" in val:
                    entity_id = val.split("/")[-1]
                    if hasattr(self, "_entity_cache") and entity_id in getattr(self, "_entity_cache", {}):
                        grounded_row[var_name] = self._entity_cache[entity_id]
                    elif entity_id in resolved:
                        grounded_row[var_name] = resolved[entity_id]
                    else:
                        try:
                            entity = self.get_entity(entity_id)
                            resolved_val = entity.label if entity and entity.label else val
                            resolved[entity_id] = resolved_val
                            grounded_row[var_name] = resolved_val
                        except Exception:
                            resolved[entity_id] = val
                            grounded_row[var_name] = val
                elif val.startswith(("+", "-")) and "T" in val and "Z" in val:
                    # Formatta date ISO 8601 di Wikidata (es. +1879-03-14T00:00:00Z -> 1879-03-14)
                    cleaned_date = val.lstrip("+").split("T")[0]
                    grounded_row[var_name] = cleaned_date
                else:
                    grounded_row[var_name] = val

            grounded_results.append(grounded_row)
        return grounded_results
