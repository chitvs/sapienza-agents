import re
from shared.ollama_client import OllamaClient
from configs.settings import settings


class SPARQLTranslator:
    """traduttore Text2SPARQL basato su LLM (Ollama) con modello dedicato alla traduzione."""

    def __init__(self, llm_client: OllamaClient | None = None, model_name: str | None = None, host: str | None = None):
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            # usa il modello di traduzione dedicato (piu' pesante) per default
            translation_model = model_name or settings.ollama_translation_model
            self.llm_client = OllamaClient(
                host=host,
                model_name=translation_model,
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

        # sposta SERVICE wikibase:label dentro il blocco WHERE se e' stato messo fuori
        service_pattern = r"(\})\s*(SERVICE\s+wikibase:label\s*\{[^}]*\})\s*$"
        service_match = re.search(service_pattern, query, re.IGNORECASE | re.DOTALL)
        if service_match:
            service_block = service_match.group(2)
            # rimuovi il SERVICE dalla posizione errata e inseriscilo prima dell'ultima }
            query = query[:service_match.start()] + "\n  " + service_block + "\n}"

        return query

    def translate(self, question: str, schema_context: str = "") -> str:
        system_prompt = self.llm_client.load_prompt(
            "translate_sparql.txt",
            schema=schema_context,
            question=question,
        )

        raw_output = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=question,
            temperature=0.0,
        )

        cleaned = OllamaClient.clean_code_block(raw_output)
        return self.sanitize_sparql(cleaned)

