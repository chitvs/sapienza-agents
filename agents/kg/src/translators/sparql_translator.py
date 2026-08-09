import re
from shared.ollama_client import OllamaClient
from configs.settings import settings
from translators.base_translator import BaseTranslator

class SPARQLTranslator(BaseTranslator):
    """Traduttore Text2SPARQL basato su LLM, indipendente dal knowledge graph."""

    # Le euristiche di riparazione sono strutturali (ragionano sul grafo della query) e
    # quindi comuni a tutti i KG SPARQL: solo la sintassi cambia, ed è isolata qui sotto
    # perché le sottoclassi la ridefiniscano senza duplicare le euristiche.
    prompt_filename: str = "translate_sparql.txt"
    entity_ref_pattern: str = r"\w+:\w+"
    property_ref_pattern: str = r"\w+:\w+"
    property_prefix: str = ""
    class_filter_pattern: str = r"\?(\w+)\s+(?:a|rdf:type)\s+[\w:]+\s*\.\s*"
    label_hint: str = "rdfs:label with an English language filter"
    # solo Wikidata genera le etichette da sé: altrove ?xLabel è una variabile mai legata,
    # che l'endpoint proietta senza valore invece di segnalare un errore
    has_label_service: bool = False

    def __init__(
        self,
        llm_client: OllamaClient | None = None,
        model_name: str | None = None,
        host: str | None = None,
    ) -> None:
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = OllamaClient(
                host=host or settings.ollama_host,
                model_name=model_name or settings.ollama_translation_model,
                timeout=settings.ollama_timeout,
                prompts_dir=settings.prompts_dir,
            )

    @staticmethod
    def sanitize_sparql(query: str) -> str:
        """Corregge gli errori di sintassi SPARQL più comuni nell'output dell'LLM."""
        # "? occupation" -> "?occupation"
        query = re.sub(r"\?\s+([a-zA-Z_]\w*)", r"?\1", query)
        # "COUNT (?x)" -> "COUNT(?x)"
        query = re.sub(r"\b(COUNT|SUM|AVG|MIN|MAX)\s+\(", r"\1(", query, flags=re.IGNORECASE)

        def fix_aggregate_alias(match: re.Match) -> str:
            """Le aggregazioni senza alias sono un errore di sintassi: ne aggiunge uno."""
            full_select = match.group(0)
            prefix_vars = match.group(1)
            expr = match.group(2).strip()
            if " AS " in expr.upper():
                return full_select
            if expr.startswith("(") and expr.endswith(")"):
                expr = expr[1:-1].strip()
            func_match = re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\b", expr, re.IGNORECASE)
            func_name = func_match.group(1).lower() if func_match else "count"
            return f"SELECT {prefix_vars}({expr} AS ?{func_name}) WHERE"

        query = re.sub(
            r"SELECT\s+(.*?)(\(?\b(?:COUNT|SUM|AVG|MIN|MAX)\([^)]+\)\)?)\s+WHERE",
            fix_aggregate_alias,
            query,
            flags=re.IGNORECASE,
        )
        # alcuni modelli generano "FROM {" al posto di "WHERE {"
        query = re.sub(r"\bFROM\s*\{", r"WHERE {", query, flags=re.IGNORECASE)
        return SPARQLTranslator._dedupe_select_vars(query)

    @staticmethod
    def _dedupe_select_vars(query: str) -> str:
        """Elimina le variabili ripetute nella SELECT, che alcuni endpoint rifiutano."""
        # capita quando il modello riusa lo stesso nome per due ruoli diversi: proiettare
        # due volte la stessa variabile non è mai intenzionale, e Virtuoso risponde
        # "column specified multiple times" invece di eseguire.
        def dedupe(match: re.Match) -> str:
            modifier = match.group(1) or ""
            variables = match.group(2).split()
            # le espressioni con parentesi (aggregazioni con alias) si lasciano intatte
            if any("(" in v for v in variables):
                return match.group(0)
            seen: list[str] = []
            for var in variables:
                if var not in seen:
                    seen.append(var)
            return f"SELECT {modifier}{' '.join(seen)} WHERE"

        return re.sub(
            r"SELECT\s+((?:DISTINCT\s+|REDUCED\s+)?)((?:\?\w+\s*)+)WHERE",
            dedupe,
            query,
            flags=re.IGNORECASE,
        )

    def postprocess(self, query: str, question: str) -> str:
        """Riparazioni post-generazione; le sottoclassi possono estenderla."""
        query = self._fix_unbound_select_label(query)
        query = self._fix_intermediate_hop_label(query)
        return self._dedupe_select_vars(query)

    def translate(self, question: str, schema_context: str = "") -> str:
        system_prompt = self.llm_client.load_prompt(
            self.prompt_filename,
            schema=schema_context,
            question=question,
        )
        raw_output = self.llm_client.chat(
            system_prompt=system_prompt,
            user_content=question,
            temperature=0.0,
        )
        cleaned = OllamaClient.clean_code_block(raw_output)
        return self.postprocess(self.sanitize_sparql(cleaned), question)

    @classmethod
    def _triple_regex(cls) -> re.Pattern[str]:
        """Riconosce una tripla del WHERE: unico punto in cui le euristiche dipendono dal KG."""
        return re.compile(
            rf'(\?\w+|{cls.entity_ref_pattern})\s+'
            rf'(?:{cls.property_ref_pattern})\s+'
            rf'(\?\w+|{cls.entity_ref_pattern}|"[^"]*")'
        )

    @classmethod
    def _leaf_vars(cls, where_body: str) -> set[str]:
        """Variabili mai usate come soggetto: le uniche che possono contenere il valore finale."""
        subject_vars: set[str] = set()
        object_vars: set[str] = set()
        for subj, obj in cls._triple_regex().findall(where_body):
            if subj.startswith("?"):
                subject_vars.add(subj[1:])
            if obj.startswith("?"):
                object_vars.add(obj[1:])
        return object_vars - subject_vars

    @classmethod
    def _constraint_vars(cls, query: str) -> set[str]:
        """Variabili usate per ordinare, raggruppare o filtrare: sono criteri di selezione, non risposte."""
        constraint_vars: set[str] = set()
        for chunk in re.findall(r"(?:ORDER\s+BY|GROUP\s+BY|HAVING|FILTER)\b[^{}]*", query, flags=re.IGNORECASE):
            constraint_vars.update(re.findall(r"\?(\w+)", chunk))
        return constraint_vars

    @classmethod
    def _replace_in_projection(cls, query: str, var: str, replacement: str) -> str:
        """Riscrive una variabile nella sola SELECT: nel WHERE cambierebbe il grafo interrogato."""
        select_match = re.search(r"\bSELECT\b(.*?)\bWHERE\b", query, flags=re.IGNORECASE | re.DOTALL)
        if not select_match:
            return query
        start, end = select_match.span(1)
        projection = re.sub(rf"\?{re.escape(var)}\b", replacement, query[start:end])
        return query[:start] + projection + query[end:]

    @classmethod
    def _project(cls, var: str) -> str:
        """Compone la proiezione di una variabile secondo le convenzioni del KG."""
        return f"?{var}Label" if cls.has_label_service else f"?{var}"

    @classmethod
    def _split_select_where(cls, query: str) -> tuple[list[str], str] | None:
        """Estrae le variabili della SELECT e il corpo del WHERE, o None se la query è malformata."""
        select_match = re.search(r"SELECT\s+(.*?)\s+WHERE\s*\{", query, flags=re.IGNORECASE | re.DOTALL)
        where_match = re.search(
            r"WHERE\s*\{(.*)\}\s*(?:ORDER BY|GROUP BY|LIMIT|$)", query, flags=re.IGNORECASE | re.DOTALL
        )
        if not select_match or not where_match:
            return None
        return re.findall(r"\?(\w+)", select_match.group(1)), where_match.group(1)

    @classmethod
    def _fix_unbound_select_label(cls, query: str) -> str:
        """Redirige ?xLabel su una variabile realmente legata nel WHERE, che altrimenti darebbe righe vuote."""
        parsed = cls._split_select_where(query)
        if parsed is None:
            return query
        select_vars, where_body = parsed
        body_vars = set(re.findall(r"\?(\w+)", where_body))

        for var in select_vars:
            if not var.endswith("Label"):
                continue
            if var in body_vars or var[: -len("Label")] in body_vars:
                continue

            candidates = {v for v in body_vars if not v.endswith("Label")}
            if len(candidates) == 1:
                query = cls._replace_in_projection(query, var, f"?{next(iter(candidates))}")
            elif len(candidates) > 1:
                # con più candidati non si sa quale sia la risposta: si selezionano tutte
                # le foglie, perché dati incerti valgono più di zero righe.
                leaves = (cls._leaf_vars(where_body) & candidates) - cls._constraint_vars(query)
                if leaves:
                    replacement = " ".join(cls._project(leaf) for leaf in sorted(leaves))
                    query = cls._replace_in_projection(query, var, replacement)
        return query

    @classmethod
    def _fix_intermediate_hop_label(cls, query: str) -> str:
        """Sposta la SELECT dall'hop intermedio alla foglia finale della catena."""
        parsed = cls._split_select_where(query)
        if parsed is None:
            return query
        select_vars, where_body = parsed

        subject_vars = {
            subj[1:] for subj, _ in cls._triple_regex().findall(where_body) if subj.startswith("?")
        }
        leaf_vars = cls._leaf_vars(where_body) - cls._constraint_vars(query)

        for var in select_vars:
            base = var[: -len("Label")] if var.endswith("Label") else var
            if base not in subject_vars:
                continue
            other_leaves = leaf_vars - {base}
            # si interviene solo con una foglia univoca, per restare conservativi
            if len(other_leaves) == 1:
                leaf = next(iter(other_leaves))
                replacement = cls._project(leaf) if var.endswith("Label") else f"?{leaf}"
                query = cls._replace_in_projection(query, var, replacement)
        return query

    @classmethod
    def relax_class_filters(cls, query: str) -> str | None:
        """Rimuove i filtri di tipo ridondanti; restituisce None se non ce ne sono di sicuri."""
        # Il predicato di tipo richiede un match esatto, non transitivo sulle sottoclassi:
        # su una variabile già raggiunta da una proprietà il filtro è ridondante e può
        # solo azzerare i risultati. Su una variabile libera (superlativi) è invece
        # l'unico vincolo: toglierlo darebbe una risposta sbagliata anziché nessuna.
        where_match = re.search(r"WHERE\s*\{(.*)\}", query, flags=re.IGNORECASE | re.DOTALL)
        reached_vars: set[str] = set()
        if where_match:
            for _, obj in cls._triple_regex().findall(where_match.group(1)):
                if obj.startswith("?"):
                    reached_vars.add(obj[1:])

        removable = [
            m for m in re.finditer(cls.class_filter_pattern, query) if m.group(1) in reached_vars
        ]
        if not removable:
            return None

        new_query = query
        for m in reversed(removable):
            new_query = new_query[: m.start()] + new_query[m.end():]
        return new_query if new_query != query else None

    @classmethod
    def _used_properties(cls, query: str) -> list[str]:
        """Estrae le proprietà citate nella query secondo la sintassi del KG."""
        return sorted(set(re.findall(rf"(?:{cls.property_ref_pattern})", query)))

    def generate_feedback_prompt(self, query: str, schema_context: str, error_context: str = "") -> str:
        used_props = self._used_properties(query)
        avoid_line = ""
        if used_props:
            avoid_line = (
                f"\nThe failed query used these properties: {', '.join(used_props)}. "
                f"Do NOT reuse the exact same combination of properties — pick a DIFFERENT property from the "
                f"VERIFIED/SUGGESTED list above for at least one step of the query (prefer a simpler, more direct "
                f"single-hop property over the one that just failed), and drop any class filter that is not "
                f"strictly required.\n"
            )
        return (
            f"the previous SPARQL query returned 0 results or failed:\n{query}\n{avoid_line}\n"
            f"try a different approach: resolve names with {self.label_hint}, "
            f"or use different properties from the schema context.\n\n"
            f"schema context:\n{schema_context}\n\n"
            f"CRITICAL: Return ONLY the raw SPARQL query wrapped in a ```sparql block. DO NOT write any conversational text."
        )

class WikidataSPARQLTranslator(SPARQLTranslator):
    """Traduttore Text2SPARQL per Wikidata: prefissi wd:/wdt: ed etichette via SERVICE wikibase:label."""

    prompt_filename = "translate_sparql.txt"
    entity_ref_pattern = r"wd:Q\d+"
    property_ref_pattern = r"wdt:P\d+|p:P\d+|ps:P\d+|pq:P\d+"
    property_prefix = "wdt:"
    class_filter_pattern = r"\?(\w+)\s+wdt:P31\s+wd:Q\d+\s*\.\s*"
    label_hint = "SERVICE wikibase:label (?xLabel / ?xDescription)"
    has_label_service = True

    @staticmethod
    def sanitize_sparql(query: str) -> str:
        """Come la versione base, ma rimette SERVICE wikibase:label dentro il WHERE se ne è uscito."""
        query = SPARQLTranslator.sanitize_sparql(query)
        service_match = re.search(
            r"(\})\s*(SERVICE\s+wikibase:label\s*\{[^}]*\})\s*(.*)$", query, re.IGNORECASE | re.DOTALL
        )
        if service_match:
            after_service = service_match.group(3).strip()
            query = query[: service_match.start()] + "\n  " + service_match.group(2) + "\n}"
            if after_service:
                query += "\n" + after_service
        return query

    @staticmethod
    def _prefer_description_over_label(query: str) -> str:
        """Sostituisce ?xLabel con ?xDescription nelle query costruite con BIND su un'entità."""
        bind_match = re.search(r"BIND\s*\(\s*wd:Q\d+\s+AS\s+\?(\w+)\s*\)", query, flags=re.IGNORECASE)
        if not bind_match:
            return query

        var_name = bind_match.group(1)
        label_var = f"?{var_name}Label"
        description_var = f"?{var_name}Description"
        if label_var in query and description_var not in query:
            query = query.replace(label_var, description_var)
        return query

    def postprocess(self, query: str, question: str) -> str:
        # per le domande descrittive la descrizione Wikidata risponde meglio dell'etichetta
        if question.lower().strip().startswith(("who is", "what is", "what are", "who was")):
            query = self._prefer_description_over_label(query)
        return super().postprocess(query, question)

class DBpediaSPARQLTranslator(SPARQLTranslator):
    """Traduttore Text2SPARQL per DBpedia: risorse dbr:, proprietà dbo:/dbp:, etichette con rdfs:label."""

    prompt_filename = "translate_sparql_dbpedia.txt"
    # le risorse possono contenere accenti, punti e parentesi (es. dbr:Mercury_(planet))
    entity_ref_pattern = r"dbr:[^\s.;,)]+|dbo:[A-Za-z]\w*"
    property_ref_pattern = r"dbo:\w+|dbp:\w+"
    property_prefix = "dbo:"
    class_filter_pattern = r"\?(\w+)\s+(?:a|rdf:type)\s+(?:dbo|yago|owl):\w+\s*\.\s*"
    label_hint = 'rdfs:label with FILTER(lang(?label) = "en")'
