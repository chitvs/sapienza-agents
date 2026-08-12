import re

from query_text import apply_outside_literals, mask_literals
from translators.base_translator import BaseTranslator

class SPARQLTranslator(BaseTranslator):
    """Traduttore Text2SPARQL."""

    # Le euristiche di riparazione sono strutturali (ragionano sul grafo della query) e
    # quindi comuni a tutti i KG SPARQL: solo la sintassi cambia, ed è isolata qui sotto
    # perché le sottoclassi la ridefiniscano senza duplicare le euristiche.
    entity_ref_pattern: str = r"\w+:\w+"
    property_ref_pattern: str = r"\w+:\w+"
    class_filter_pattern: str = r"\?(\w+)\s+(?:a|rdf:type)\s+[\w:]+\s*\.\s*"
    label_hint: str = "rdfs:label with an English language filter"
    # solo Wikidata genera le etichette da sé: altrove ?xLabel è una variabile mai legata,
    # che l'endpoint proietta senza valore invece di segnalare un errore
    has_label_service: bool = False

    @classmethod
    def sanitize(cls, query: str) -> str:
        """Corregge gli errori di sintassi SPARQL più comuni nell'output dell'LLM."""
        def normalize_spacing(code: str) -> str:
            # "? occupation" -> "?occupation"
            code = re.sub(r"\?\s+([a-zA-Z_]\w*)", r"?\1", code)
            # "COUNT (?x)" -> "COUNT(?x)"
            return re.sub(r"\b(COUNT|SUM|AVG|MIN|MAX)\s+\(", r"\1(", code, flags=re.IGNORECASE)

        query = apply_outside_literals(query, normalize_spacing)

        def fix_aggregate_alias(match: re.Match) -> str:
            """Le aggregazioni senza alias sono un errore di sintassi: ne aggiunge uno."""
            prefix_vars, func, arg = match.groups()
            return f"SELECT {prefix_vars}({func}({arg}) AS ?{func.lower()}) WHERE"

        # l'aggregazione già dotata di alias non combacia: fra la parentesi chiusa e WHERE
        # ci sarebbe " AS ?x)", quindi il pattern la ignora senza bisogno di controlli
        query = re.sub(
            r"SELECT\s+(.*?)\(?\b(COUNT|SUM|AVG|MIN|MAX)\(([^)]+)\)\)?\s+WHERE",
            fix_aggregate_alias,
            query,
            flags=re.IGNORECASE,
        )
        # alcuni modelli generano "FROM {" al posto di "WHERE {"
        query = re.sub(r"\bFROM\s*\{", r"WHERE {", query, flags=re.IGNORECASE)
        return cls._dedupe_select_vars(query)

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

    @classmethod
    def _triple_regex(cls) -> re.Pattern[str]:
        """Riconosce una tripla del WHERE: unico punto in cui le euristiche dipendono dal KG."""
        return re.compile(
            rf'(\?\w+|{cls.entity_ref_pattern})\s+'
            rf'(?:{cls.property_ref_pattern})\s+'
            rf'(\?\w+|{cls.entity_ref_pattern}|"[^"]*")'
        )

    @classmethod
    def _has_unparsed_syntax(cls, where_body: str) -> bool:
        """Segnala le forme sintattiche che _triple_regex non sa leggere."""
        # con le triple abbreviate (";") o i property path gli oggetti intermedi non
        # compaiono nell'analisi, e le foglie dedotte sarebbero sbagliate: meglio non
        # riscrivere nulla che riscrivere la proiezione su una variabile scorretta,
        # perché la query resterebbe valida rispondendo però a un'altra domanda
        body = mask_literals(where_body)
        if ";" in body:
            return True
        return bool(re.search(rf"(?:{cls.property_ref_pattern})\s*[/|*+]", body))

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
            elif len(candidates) > 1 and not cls._has_unparsed_syntax(where_body):
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
        if cls._has_unparsed_syntax(where_body):
            return query

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
    def relax_constraints(cls, query: str) -> str | None:
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

    def generate_feedback_prompt(self, query: str, schema_context: str) -> str:
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
    correction_prompt_filename = "correction.txt"
    entity_ref_pattern = r"wd:Q\d+"
    property_ref_pattern = r"wdt:P\d+|p:P\d+|ps:P\d+|pq:P\d+"
    class_filter_pattern = r"\?(\w+)\s+wdt:P31\s+wd:Q\d+\s*\.\s*"
    label_hint = "SERVICE wikibase:label (?xLabel / ?xDescription)"
    has_label_service = True

    @staticmethod
    def _where_span(query: str) -> tuple[int, int] | None:
        """Indici della graffa che apre il WHERE e di quella che lo chiude, o None."""
        match = re.search(r"\bWHERE\s*\{", query, flags=re.IGNORECASE)
        if not match:
            return None
        masked = mask_literals(query)
        opening = match.end() - 1
        depth = 0
        for i in range(opening, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    return opening, i
        return None

    @classmethod
    def sanitize(cls, query: str) -> str:
        """Come la versione base, ma rimette SERVICE wikibase:label dentro il WHERE se ne è uscito."""
        query = super().sanitize(query)
        service_match = re.search(
            r"SERVICE\s+wikibase:label\s*\{[^{}]*\}", query, flags=re.IGNORECASE
        )
        span = cls._where_span(query)
        if not service_match or span is None:
            return query

        # Se il blocco è già dentro il WHERE va lasciato dov'è: la versione precedente si
        # agganciava alla prima graffa chiusa che lo precedeva, e con un UNION o un
        # OPTIONAL lo infilava dentro il ramo. Le graffe restavano bilanciate, quindi
        # nessun errore di sintassi, ma le etichette dell'altro ramo uscivano vuote.
        opening, closing = span
        if opening < service_match.start() < closing:
            return query

        service = service_match.group(0)
        without_service = query[: service_match.start()] + query[service_match.end():]
        span = cls._where_span(without_service)
        if span is None:
            return query
        _, closing = span
        rebuilt = without_service[:closing] + "\n  " + service + "\n" + without_service[closing:]
        return rebuilt.rstrip()

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
    correction_prompt_filename = "correction_dbpedia.txt"
    # le risorse possono contenere accenti, punti e parentesi (es. dbr:Mercury_(planet))
    entity_ref_pattern = r"dbr:[^\s.;,)]+|dbo:[A-Za-z]\w*"
    property_ref_pattern = r"dbo:\w+|dbp:\w+"
    class_filter_pattern = r"\?(\w+)\s+(?:a|rdf:type)\s+(?:dbo|yago|owl):\w+\s*\.\s*"
    label_hint = 'rdfs:label with FILTER(lang(?label) = "en")'
