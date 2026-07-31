from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class PrunedSchema:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    context_text: str = ""

class BasePruner(ABC):
    """classe astratta base per gli schema pruner."""

    @abstractmethod
    def prune(
        self,
        seed_entity_ids: list[str],
        connector_or_client: Any = None,
        max_items: int = 40,
        question: str = "",
    ) -> PrunedSchema:
        """estrae e formatta il contesto di schema prunato per l'LLM."""
        raise NotImplementedError

    def format_entity_context(
        self,
        entity_data: Any,
        props_sample: list[tuple[str, list[Any]]],
        connector_or_client: Any = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """formatta l'intestazione, le proprietà e i collegamenti dell'entità per il testo di contesto dell'LLM."""
        edges = []
        desc_str = f" - {entity_data.description}" if getattr(entity_data, "description", "") else ""
        header = f"entità: wd:{entity_data.id} ({entity_data.label}{desc_str})"

        if getattr(entity_data, "description", ""):
            header += f"\ndescrizione wikidata: \"{entity_data.description}\""

        if props_sample:
            props_formatted = []
            for prop_key, vals in props_sample:
                p_id = prop_key.split(" ")[0]
                formatted_vals = []
                for val in vals[:2]:
                    val_str = str(val)
                    if val_str.startswith("Q") and connector_or_client and hasattr(connector_or_client, "get_entity"):
                        try:
                            val_ent = connector_or_client.get_entity(val_str)
                            if val_ent and val_ent.label:
                                formatted_vals.append(f"{val_ent.label} ({val_str})")
                            else:
                                formatted_vals.append(val_str)
                        except Exception:
                            formatted_vals.append(val_str)
                    else:
                        formatted_vals.append(val_str)
                    edges.append({"source": entity_data.id, "prop": p_id, "target": val_str})

                props_formatted.append(f"wdt:{p_id} [{prop_key}] (valori: {formatted_vals})")

            header += f"\nproprietà: [{', '.join(props_formatted)}]"

        return header, edges
