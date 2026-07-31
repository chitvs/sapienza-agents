from typing import Any
from pruners.base_pruner import BasePruner, PrunedSchema

class KHopPruner(BasePruner):
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

                props_sample = list(entity_data.properties.items())[:max_items] if entity_data.properties else []
                header, entity_edges = self.format_entity_context(
                    entity_data=entity_data,
                    props_sample=props_sample,
                    connector_or_client=connector_or_client,
                )
                edges.extend(entity_edges)
                context_lines.append(header)

        if not context_lines:
            for seed_id in seed_entity_ids:
                context_lines.append(f"entità: wd:{seed_id}")

        return PrunedSchema(
            nodes=nodes,
            edges=edges,
            context_text="\n".join(context_lines),
        )
