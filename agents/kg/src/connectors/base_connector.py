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
                val = var_data.get("value", "") if isinstance(var_data, dict) else str(var_data)

                # se il valore è un uri wikidata (es. http://www.wikidata.org/entity/Q937)
                if "wikidata.org/entity/Q" in val:
                    qid = val.split("/")[-1]
                    if qid in resolved:
                        grounded_row[var_name] = resolved[qid]
                    else:
                        try:
                            entity = self.get_entity(qid)
                            resolved_val = entity.label if entity and entity.label else val
                            resolved[qid] = resolved_val
                            grounded_row[var_name] = resolved_val
                        except Exception:
                            resolved[qid] = val
                            grounded_row[var_name] = val
                else:
                    grounded_row[var_name] = val

            grounded_results.append(grounded_row)
        return grounded_results
