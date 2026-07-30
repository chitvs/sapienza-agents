import re
from shared.ollama_client import OllamaClient


class SPARQLTranslator:
    """traduttore Text2SPARQL basato su LLM (Ollama)."""

    def __init__(self, llm_client: OllamaClient | None = None, model_name: str | None = None, host: str | None = None):
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = OllamaClient(
                host=host,
                model_name=model_name,
            )

    @staticmethod
    def sanitize_sparql(query: str) -> str:
        """Sanitizza e corregge errori comuni di sintassi SPARQL generati dall'LLM."""
        # Rimuovi lo spazio tra '?' e il nome della variabile (es. ? occupation -> ?occupation)
        query = re.sub(r"\?\s+([a-zA-Z_]\w*)", r"?\1", query)

        # Rimuovi lo spazio errato tra funzioni di aggregazione e parentesi (es. COUNT (?) -> COUNT(?))
        query = re.sub(r"\b(COUNT|SUM|AVG|MIN|MAX)\s+\(", r"\1(", query, flags=re.IGNORECASE)

        # Assicura che le funzioni di aggregazione nella SELECT abbiano un alias (es. COUNT(?x) -> (COUNT(?x) AS ?count))
        def fix_aggregate_alias(match):
            full_select = match.group(0)
            expr = match.group(1).strip()
            if " AS " in expr.upper():
                return full_select
            if expr.startswith("(") and expr.endswith(")"):
                expr = expr[1:-1].strip()
            func_match = re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\b", expr, re.IGNORECASE)
            func_name = func_match.group(1).lower() if func_match else "count"
            return f"SELECT ({expr} AS ?{func_name}) WHERE"

        query = re.sub(r"SELECT\s+(\(?\b(?:COUNT|SUM|AVG|MIN|MAX)\([^)]+\)\)?)\s+WHERE", fix_aggregate_alias, query, flags=re.IGNORECASE)

        # Correggi variabili SELECT non vincolate nel WHERE
        select_match = re.search(r"SELECT\s+((?:(?:\((?:COUNT|SUM|AVG|MIN|MAX)\([^)]+\)\s+AS\s+\?\w+\)|\?\w+)\s*)+)WHERE", query, re.IGNORECASE)
        if select_match:
            select_clause = select_match.group(1)
            where_body = query[select_match.end():]
            where_vars = set(re.findall(r"\?\w+", where_body))

            select_vars = re.findall(r"\?\w+", select_clause)
            for var in select_vars:
                if var not in where_vars and where_vars:
                    first_where_var = list(where_vars)[0]
                    query = query.replace(var, first_where_var)

        return query

    def translate(self, question: str, schema_context: str = "") -> str:
        system_prompt = self.llm_client.load_prompt("translate_sparql.txt")
        user_content = f"Domanda: {question}\n\nEvidenze/Contesto:\n{schema_context}"

        raw_output = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.0,
        )

        cleaned = OllamaClient.clean_code_block(raw_output)
        return self.sanitize_sparql(cleaned)
