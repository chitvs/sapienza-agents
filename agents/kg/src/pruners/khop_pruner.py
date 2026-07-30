from dataclasses import dataclass, field
from typing import Any

@dataclass
class PrunedSchema:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    context_text: str = ""

class KHopPruner:
    """schema pruner per l'estrazione delle proprietà e delle relazioni dell'entità per l'llm."""

    def prune(
        self,
        seed_entity_ids: list[str],
        connector_or_client: Any = None,
        max_items: int = 40,
        question: str = "",
    ) -> PrunedSchema:
        if not seed_entity_ids:
            return PrunedSchema(context_text="")

        nodes = []
        edges = []
        context_lines = []
        visited_ids = set()

        if connector_or_client and hasattr(connector_or_client, "get_entity"):
            for seed_id in seed_entity_ids:
                if seed_id in visited_ids:
                    continue
                visited_ids.add(seed_id)

                entity_data = connector_or_client.get_entity(seed_id)
                if not entity_data:
                    continue

                nodes.append({"id": entity_data.id, "label": entity_data.label})
                line = f"entità: wd:{entity_data.id} ({entity_data.label})"

                if entity_data.properties:
                    props_sample = list(entity_data.properties.items())[:max_items]
                    props_str = ", ".join([f"wdt:{p_id} (valori: {vals[:2]})" for p_id, vals in props_sample])
                    line += f" -> proprietà disponibili: [{props_str}]"

                    for prop_id, vals in props_sample:
                        for val in vals[:2]:
                            edges.append({"source": entity_data.id, "prop": prop_id, "target": val})

                context_lines.append(line)

        if not context_lines:
            for seed_id in seed_entity_ids:
                context_lines.append(f"entità: wd:{seed_id}")

        return PrunedSchema(
            nodes=nodes,
            edges=edges,
            context_text="\n".join(context_lines),
        )
