import logging
from typing import Any

from pruners.base_pruner import BasePruner, PrunedSchema

logger = logging.getLogger(__name__)

class Neo4jSchemaPruner(BasePruner):
    """Espone al modello l'intero schema del grafo, letto per introspezione."""

    # A differenza di Wikidata, dove servono migliaia di proprietà e quindi una ricerca
    # semantica, lo schema di un grafo Neo4j è piccolo e chiuso: passarlo tutto elimina
    # in partenza il rischio che il modello inventi relazioni inesistenti.

    @staticmethod
    def _format_property(prop: Any) -> str:
        """Rende una proprietà come "nome: TIPO", accettando anche la forma senza tipo."""
        if isinstance(prop, dict):
            name = prop.get("name", "")
            prop_type = prop.get("type")
            return f"{name}: {prop_type}" if prop_type else str(name)
        return str(prop)

    def _format_schema(self, schema: dict[str, Any]) -> list[str]:
        """Formatta label e relazioni del grafo per il contesto dell'LLM."""
        lines: list[str] = []
        labels = schema.get("labels") or {}
        relationships = schema.get("relationships") or []

        if labels:
            lines.append("NODE LABELS (with their properties and types):")
            for label, props in labels.items():
                props_str = ", ".join(self._format_property(p) for p in props) if props else "(no properties)"
                lines.append(f"  (:{label}) properties: {props_str}")

        if relationships:
            lines.append("")
            lines.append("RELATIONSHIP TYPES (direction matters):")
            for rel in relationships:
                lines.append(f"  (:{rel.get('from') or '?'})-[:{rel.get('type')}]->(:{rel.get('to') or '?'})")
        return lines

    def prune(
        self,
        seed_entity_ids: list[str],
        connector_or_client: Any = None,
        max_items: int = 40,  # ignorato: lo schema si legge per intero
        question: str = "",
        max_hops: int = 2,  # ignorato: lo schema si legge, non si attraversa
    ) -> PrunedSchema:
        """Costruisce il contesto unendo lo schema del grafo e le entità già risolte."""
        schema: dict[str, Any] = {}
        if connector_or_client is not None and hasattr(connector_or_client, "get_schema"):
            try:
                schema = connector_or_client.get_schema()
            except Exception as err:
                logger.warning("lettura schema neo4j fallita: %s", err)

        context_lines = self._format_schema(schema)

        if seed_entity_ids and connector_or_client is not None and hasattr(connector_or_client, "get_entity"):
            seed_lines: list[str] = []
            for seed_id in seed_entity_ids:
                try:
                    entity_data = connector_or_client.get_entity(seed_id)
                except Exception as err:
                    logger.warning("lettura entità seed '%s' fallita: %s", seed_id, err)
                    continue
                if not entity_data or not getattr(entity_data, "label", ""):
                    continue

                node_labels = entity_data.description or ""
                label_pattern = f":{node_labels.split(',')[0].strip()}" if node_labels else ""
                seed_lines.append(f'  ({label_pattern} {{name/title: "{entity_data.label}"}})')

            if seed_lines:
                context_lines.append("")
                context_lines.append("ENTITIES MENTIONED IN THE QUESTION (already resolved in the graph):")
                context_lines.extend(seed_lines)

        return PrunedSchema(context_text="\n".join(context_lines))
