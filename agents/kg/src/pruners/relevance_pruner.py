import re
from typing import Any
from pruners.base_pruner import BasePruner, PrunedSchema

class RelevancePruner(BasePruner):
    """
    schema pruner intelligente e multilingua che ordina e filtra le proprietà
    dell'entità in base alla loro rilevanza semantica rispetto alla domanda dell'utente.
    senza alcun hardcoding o liste statiche di proprietà.
    """

    @staticmethod
    def score_property(q_tokens: set[str], prop_key: str, values: list[Any]) -> float:
        if not q_tokens:
            return 0.0

        p_tokens = set(re.findall(r"\w+", prop_key.lower()))

        # Sovrapposizione diretta dei token
        overlap = len(q_tokens.intersection(p_tokens))
        score = float(overlap * 3.0)

        # Match di sottostringa per parole con più di 3 caratteri
        prop_clean = re.sub(r"^P\d+\s*\(|\)$", "", prop_key).lower()
        for qt in q_tokens:
            if len(qt) > 3 and (qt in prop_clean or prop_clean in qt):
                score += 2.0

        # Penalizza proprietà di identificativi esterni (es. "ID", "identifier")
        is_id_prop = " id" in prop_clean or "identifier" in prop_clean or prop_clean.endswith(" id")
        if is_id_prop:
            score -= 5.0

        # Controllo match sui valori solo se NON è un identificativo esterno
        if not is_id_prop:
            for val in values[:3]:
                val_str = str(val).lower()
                for qt in q_tokens:
                    if len(qt) > 3 and qt in val_str:
                        score += 1.5

        # Boost per valori semantici strutturali (entità collegate Q, URI http o date)
        if any(str(v).startswith("Q") or str(v).startswith("http") or "-" in str(v) for v in values):
            score += 1.5

        return score

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
            q_tokens = set(re.findall(r"\w+", question.lower())) if question else set()
            for seed_id in seed_entity_ids:
                if seed_id in visited_ids:
                    continue
                visited_ids.add(seed_id)

                entity_data = connector_or_client.get_entity(seed_id)
                if not entity_data:
                    continue

                nodes.append({"id": entity_data.id, "label": entity_data.label})

                if entity_data.properties:
                    # Ordina le proprietà in base alla rilevanza semantica rispetto alla domanda
                    scored_props = sorted(
                        entity_data.properties.items(),
                        key=lambda item: self.score_property(q_tokens, item[0], item[1]),
                        reverse=True,
                    )
                    props_sample = scored_props[:max_items]
                else:
                    props_sample = []

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
