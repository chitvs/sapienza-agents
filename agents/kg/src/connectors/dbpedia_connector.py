import html
import logging
import re
import time
from typing import Any
from urllib.parse import unquote
import requests
from configs.settings import settings
from connectors.base_connector import (
    BaseConnector,
    EntityCandidate,
    EntityData,
    KnowledgeGraphUnavailableError,
)

# configurazione logger
logger = logging.getLogger(__name__)

# variabili globali
DBPEDIA_LOOKUP_API = "https://lookup.dbpedia.org/api/search"
DBPEDIA_RESOURCE_NS = "http://dbpedia.org/resource/"
DBPEDIA_ONTOLOGY_NS = "http://dbpedia.org/ontology/"

# caratteri ammessi in un nome prefissato SPARQL.
_SAFE_LOCAL_NAME = re.compile(r"^[A-Za-z0-9_\-.%]+$")

class DBpediaConnector(BaseConnector):
    """Connettore verso DBpedia."""

    # si usa dbo: (l'ontologia curata e tipizzata) invece di dbp: (estratto dalle infobox)
    entity_prefix = "dbr:"
    property_prefix = "dbo:"
    class_prefix = "dbo:"
    max_cache_size = 1000

    def __init__(self, language: str = "en") -> None:
        self.language = language
        self.timeout = settings.dbpedia_timeout
        self.endpoint = settings.dbpedia_endpoint
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)"})
        self._entity_cache: dict[str, EntityData] = {}
        self._search_cache: dict[str, list[EntityCandidate]] = {}
        self._reference_counts: dict[str, float] = {}

    @staticmethod
    def _local_name(uri: str) -> str:
        """Estrae il nome locale da un URI DBpedia."""
        if uri.startswith(DBPEDIA_RESOURCE_NS):
            return uri[len(DBPEDIA_RESOURCE_NS):]
        if uri.startswith(DBPEDIA_ONTOLOGY_NS):
            return uri[len(DBPEDIA_ONTOLOGY_NS):]
        return uri.rsplit("/", 1)[-1] if "/" in uri else uri

    @staticmethod
    def _strip_highlight(text: str) -> str:
        """Rimuove i tag <B> con cui la Lookup API evidenzia i termini cercati."""
        return html.unescape(re.sub(r"</?B>", "", text or "")).strip()

    @staticmethod
    def _readable(local_name: str) -> str:
        """Rende leggibile un nome locale: 'Princeton,_New_Jersey' -> 'Princeton, New Jersey'."""
        return unquote(local_name).replace("_", " ").strip()

    def format_entity_ref(self, entity_id: str) -> str:
        """Cita la risorsa come dbr:Nome se lecito, altrimenti con l'URI completo."""
        if _SAFE_LOCAL_NAME.match(entity_id):
            return f"{self.entity_prefix}{entity_id}"
        return f"<{DBPEDIA_RESOURCE_NS}{entity_id}>"

    def _run_sparql(self, query: str) -> list[dict[str, Any]]:
        """Esegue una query di servizio sull'endpoint pubblico, con un retry sul rate limit."""
        for attempt in range(2):
            try:
                response = self.session.get(
                    self.endpoint,
                    params={"query": query, "format": "application/sparql-results+json"},
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json().get("results", {}).get("bindings", [])
            except Exception as err:
                if attempt == 0:
                    logger.debug("query dbpedia fallita, ritento: %s", err)
                    time.sleep(1.5)
                    continue
                raise KnowledgeGraphUnavailableError("dbpedia", str(err)) from err
        raise KnowledgeGraphUnavailableError("dbpedia", "nessuna risposta dall'endpoint")

    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """Cerca entità con la Lookup API, che indicizza etichette e abstract."""
        if not text or not text.strip():
            return []

        cache_key = f"{text.strip().lower()}:{limit}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        try:
            response = self.session.get(
                DBPEDIA_LOOKUP_API,
                params={"query": text, "maxResults": limit, "format": "json"},
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            docs = response.json().get("docs", [])
        except Exception as err:
            # senza candidati la pipeline procederebbe senza entità ancorate
            raise KnowledgeGraphUnavailableError("dbpedia", str(err)) from err

        def first(doc: dict, key: str) -> str:
            """La Lookup API restituisce ogni campo come lista di un elemento."""
            value = doc.get(key)
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return str(value) if value is not None else ""

        candidates = []
        for doc in docs:
            uri = first(doc, "resource")
            if not uri:
                continue
            local = self._local_name(uri)
            description = self._strip_highlight(first(doc, "comment"))[:250]
            type_name = self._strip_highlight(first(doc, "typeName"))
            if type_name:
                description = f"{type_name}: {description}" if description else type_name
            try:
                ref_count = float(first(doc, "refCount") or 0.0)
            except ValueError:
                ref_count = 0.0
            # il limite è per candidato, non per ricerca
            self._set_cache_entry(
                self._reference_counts, local, ref_count,
                limit=self.max_cache_size * settings.linker_candidates,
            )
            candidates.append(
                EntityCandidate(
                    id=local,
                    label=self._strip_highlight(first(doc, "label")) or self._readable(local),
                    description=description,
                )
            )

        self._set_cache_entry(self._search_cache, cache_key, candidates)
        return candidates

    def candidate_prominence(self, candidates: list[EntityCandidate]) -> dict[str, float]:
        """Numero di risorse che puntano al candidato, letto dalla Lookup API durante la ricerca."""
        # o si conoscono tutti o nessuno
        counts = {c.id: self._reference_counts.get(c.id) for c in candidates}
        return {} if any(v is None for v in counts.values()) else counts

    def is_valid_candidate(self, candidate: EntityCandidate) -> bool:
        """Scarta le pagine di disambiguazione e le categorie, che non sono entità."""
        # senza questo filtro finiscono fra i candidati passati al disambiguatore e possono
        # essere scelte come entità seed, ancorando la query a una pagina di servizio
        identifier = candidate.id
        if not identifier:
            return False
        if identifier.startswith(("Category:", "List_of_", "Template:")):
            return False
        return "(disambiguation)" not in identifier.lower()

    def get_entity(self, entity_id: str) -> EntityData:
        """Legge etichetta e proprietà dell'ontologia dbo: di una risorsa."""
        if entity_id in self._entity_cache:
            return self._entity_cache[entity_id]

        ref = self.format_entity_ref(entity_id)
        # si escludono: i link di navigazione wiki e i testi lunghi (rumore che
        # saturerebbe il contesto) e i letterali in lingue diverse da quella richiesta,
        # perché dbpedia replica molte proprietà testuali in decine di lingue.
        query = f"""
        SELECT ?p ?o WHERE {{
          {ref} ?p ?o .
          FILTER(STRSTARTS(STR(?p), "{DBPEDIA_ONTOLOGY_NS}"))
          FILTER(?p NOT IN (
            <{DBPEDIA_ONTOLOGY_NS}wikiPageWikiLink>,
            <{DBPEDIA_ONTOLOGY_NS}wikiPageExternalLink>,
            <{DBPEDIA_ONTOLOGY_NS}abstract>,
            <{DBPEDIA_ONTOLOGY_NS}thumbnail>,
            <{DBPEDIA_ONTOLOGY_NS}wikiPageID>,
            <{DBPEDIA_ONTOLOGY_NS}wikiPageRevisionID>,
            <{DBPEDIA_ONTOLOGY_NS}wikiPageLength>
          ))
          FILTER(!isLiteral(?o) || lang(?o) = "" || lang(?o) = "{self.language}")
        }} LIMIT 200
        """
        rows = self._run_sparql(query)

        properties: dict[str, list[str]] = {}
        for row in rows:
            prop_uri = row.get("p", {}).get("value", "")
            obj = row.get("o", {}).get("value", "")
            if not prop_uri or not obj:
                continue
            prop_name = self._local_name(prop_uri)
            value = self._local_name(obj) if obj.startswith(DBPEDIA_RESOURCE_NS) else obj
            properties.setdefault(prop_name, []).append(value)

        label_rows = self._run_sparql(
            f'SELECT ?label WHERE {{ {ref} rdfs:label ?label . '
            f'FILTER(lang(?label) = "{self.language}") }} LIMIT 1'
        )
        label = label_rows[0]["label"]["value"] if label_rows else self._readable(entity_id)

        entity = EntityData(
            id=entity_id,
            label=label,
            description="",
            properties=properties,
        )

        self._set_cache_entry(self._entity_cache, entity_id, entity)
        return entity

    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Converte i binding SPARQL in valori leggibili."""
        # le ASK restituiscono un booleano, non binding
        if len(raw_results) == 1 and set(raw_results[0]) == {"boolean"}:
            return [dict(raw_results[0])]

        # l'URI contiene già il nome dell'entità, quindi l'etichetta si ricava dal nome locale
        grounded = []
        for row in raw_results:
            clean_row: dict[str, Any] = {}
            sources: dict[str, str] = {}
            for key, binding in row.items():
                value = binding.get("value", "") if isinstance(binding, dict) else binding
                if isinstance(value, str) and value.startswith(DBPEDIA_RESOURCE_NS):
                    # l'uri originale si conserva a parte
                    sources[key] = value
                    value = self._readable(self._local_name(value))
                clean_row[key] = value
            if sources:
                clean_row["_sources"] = sources
            grounded.append(clean_row)
        return grounded
