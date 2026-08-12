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
    def _format_schema(schema: dict[str, Any]) -> list[str]:
        """Formatta label e relazioni del grafo per il contesto dell'LLM."""
        lines: list[str] = []
        labels = schema.get("labels") or {}
        relationships = schema.get("relationships") or []

        if labels:
            lines.append("NODE LABELS (with their properties and types):")
            for label, props in labels.items():
                props_str = ", ".join(f"{p['name']}: {p['type']}" for p in props) if props else "(no properties)"
                lines.append(f"  (:{label}) properties: {props_str}")

        if relationships:
            lines.append("")
            lines.append("RELATIONSHIP TYPES (direction matters):")
            for rel in relationships:
                lines.append(f"  (:{rel.get('from') or '?'})-[:{rel.get('type')}]->(:{rel.get('to') or '?'})")
        return lines

    def prune(self, seed_entity_ids: list[str], question: str = "") -> PrunedSchema:
        """Costruisce il contesto unendo lo schema del grafo e le entità già risolte."""
        context_lines = self._format_schema(self.connector.get_schema())

        if seed_entity_ids:
            try:
                seed_entities = self.connector.get_entities(seed_entity_ids).values()
            except Exception as err:
                logger.warning("entità seed non leggibili dal grafo: %s", err)
                seed_entities = []

            seed_lines = []
            for entity_data in seed_entities:
                if not entity_data.label:
                    continue
                node_labels = entity_data.description or ""
                label_pattern = f":{node_labels.split(',')[0].strip()}" if node_labels else ""
                seed_lines.append(f'  ({label_pattern} {{name/title: "{entity_data.label}"}})')

            if seed_lines:
                context_lines.append("")
                context_lines.append("ENTITIES MENTIONED IN THE QUESTION (already resolved in the graph):")
                context_lines.extend(seed_lines)

        return PrunedSchema(context_text="\n".join(context_lines))
