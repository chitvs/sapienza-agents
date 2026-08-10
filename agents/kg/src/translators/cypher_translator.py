import re

from shared.ollama_client import OllamaClient
from translators.base_translator import BaseTranslator

class CypherTranslator(BaseTranslator):
    """Traduttore Text2Cypher basato su LLM per grafi Neo4j."""

    @staticmethod
    def sanitize(query: str) -> str:
        """Normalizza gli errori di forma più comuni nell'output dell'LLM."""
        # il punto e virgola finale è rifiutato dentro una transazione esplicita
        query = query.strip().rstrip(";").strip()
        # spazi spuri nei pattern, es. "( p:Person )"
        query = re.sub(r"\(\s+", "(", query)
        return re.sub(r"\s+\)", ")", query)

    def translate(
        self,
        question: str,
        schema_context: str = "",
        temperature: float = 0.0,
        top_p: float | None = None,
    ) -> str:
        system_prompt = self.llm_client.load_prompt(
            "translate_cypher.txt",
            schema=schema_context,
            question=question,
        )
        raw_output = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=question,
            temperature=temperature,
            top_p=top_p,
        )
        return self.postprocess(self.sanitize(OllamaClient.clean_code_block(raw_output)), question)

    def generate_feedback_prompt(self, query: str, schema_context: str) -> str:
        hints: list[str] = [
            "The query was syntactically valid but matched nothing, so the problem is in "
            "WHAT it matches, not in how it is written. You MUST change something: "
            "returning the same query again is never a valid answer."
        ]

        used_rels = sorted(set(re.findall(r"\[:(\w+)\]", query)))
        if used_rels:
            hints.append(
                f"It used these relationship types: {', '.join(used_rels)}. Check them against "
                f"the schema and change the type or the ARROW DIRECTION for at least one step — "
                f"traversing a relationship the wrong way is the most common cause of zero rows."
            )

        # seconda causa tipica di zero righe: valori del tipo sbagliato nei filtri inline
        # (es. {released: true} su una proprietà intera) invece di una clausola WHERE
        inline_filters = re.findall(r"\{\s*(\w+)\s*:\s*([^}]+)\}", query)
        if inline_filters:
            rendered = ", ".join(f"{{{k}: {v.strip()}}}" for k, v in inline_filters)
            hints.append(
                f"It filtered inline with {rendered}. Verify each of these against the property "
                f"TYPES in the schema: a filter whose value has the wrong type (for example a "
                f"boolean on an integer property) matches nothing. If you only need the property "
                f"to exist, drop the inline filter and use `WHERE n.prop IS NOT NULL` instead; "
                f"if you need to compare it, use a WHERE clause with a value of the right type."
            )

        avoid_line = "\n" + "\n".join(f"- {h}" for h in hints) + "\n"
        return (
            f"the previous Cypher query returned 0 results or failed:\n{query}\n{avoid_line}\n"
            f"try a different approach using ONLY the labels and relationship types listed in "
            f"the schema below.\n\n"
            f"graph schema:\n{schema_context}\n\n"
            f"CRITICAL: Return ONLY the raw Cypher query wrapped in a ```cypher block. "
            f"DO NOT write any conversational text."
        )
