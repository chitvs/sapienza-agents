import logging
from typing import Any

from connectors.base_connector import (
    BaseConnector,
    EntityCandidate,
    EntityData,
    KnowledgeGraphUnavailableError,
)

logger = logging.getLogger(__name__)

# Chiavi con cui un umano (e quindi anche l'LLM) identifica un nodo scrivendo Cypher,
# in ordine di preferenza: (:Person {name: ...}), (:Movie {title: ...}).
_NAME_PROPERTIES = ("name", "title", "label")

# Lo schema di un grafo è regolare, quindi un campione piccolo basta a dedurre le
# proprietà di una label senza pesare sui database grandi.
_SCHEMA_SAMPLE_SIZE = 100

class Neo4jConnector(BaseConnector):
    """Connettore verso un'istanza Neo4j: cerca le entità interrogando il grafo stesso."""

    # su Neo4j i nodi si citano per label e proprietà, senza prefissi di namespace
    entity_prefix = ""
    property_prefix = ""

    def __init__(
        self,
        executor: Any = None,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        if executor is not None:
            self.executor = executor
        else:
            from configs.settings import settings
            from executors.cypher_executor import CypherExecutor

            self.executor = CypherExecutor(
                uri=uri or settings.neo4j_uri,
                user=user or settings.neo4j_user,
                password=password or settings.neo4j_password,
            )
        self._schema_cache: dict[str, Any] | None = None

    @staticmethod
    def _natural_name(props: dict[str, Any]) -> str:
        """Estrae il nome leggibile di un nodo dalle sue proprietà."""
        for key in _NAME_PROPERTIES:
            value = props.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in props.values():
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _run(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Esegue una query di servizio del connettore."""
        return self.executor.run_internal(query, params)

    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """Cerca nodi per nome, dando la precedenza al match esatto su quello parziale."""
        if not text or not text.strip():
            return []

        # senza l'ordinamento per rank, cercare "The Matrix" restituirebbe prima i
        # sequel il cui titolo contiene la stringa che non il film omonimo
        query = """
        MATCH (n)
        WITH n, [k IN $name_props WHERE n[k] IS NOT NULL] AS name_keys
        WHERE size(name_keys) > 0
        WITH n, toString(n[name_keys[0]]) AS name
        WHERE toLower(name) = toLower($text) OR toLower(name) CONTAINS toLower($text)
        RETURN elementId(n) AS id,
               name,
               labels(n) AS labels,
               CASE WHEN toLower(name) = toLower($text) THEN 0 ELSE 1 END AS rank
        ORDER BY rank, size(name)
        LIMIT $limit
        """
        try:
            rows = self._run(query, {"text": text, "limit": limit, "name_props": list(_NAME_PROPERTIES)})
        except Exception as err:
            raise KnowledgeGraphUnavailableError("neo4j", str(err)) from err

        return [
            EntityCandidate(
                id=str(row.get("id", "")),
                label=row.get("name", ""),
                description=", ".join(row.get("labels") or []),
            )
            for row in rows
        ]

    def get_entity(self, entity_id: str) -> EntityData:
        """Recupera un nodo con le sue proprietà e relazioni uscenti."""
        query = """
        MATCH (n) WHERE elementId(n) = $id
        OPTIONAL MATCH (n)-[r]->(m)
        WITH n, type(r) AS rel_type, collect(DISTINCT m)[..5] AS targets
        RETURN properties(n) AS props,
               labels(n) AS labels,
               collect({rel: rel_type, targets: [t IN targets | properties(t)]}) AS rels
        """
        try:
            rows = self._run(query, {"id": entity_id})
        except Exception as err:
            raise KnowledgeGraphUnavailableError("neo4j", str(err)) from err

        if not rows:
            return EntityData(id=entity_id, label=entity_id, description="", properties={})

        props = rows[0].get("props") or {}
        labels = rows[0].get("labels") or []
        properties: dict[str, list[str]] = {key: [str(value)] for key, value in props.items()}

        # le relazioni entrano in 'properties' con la forma usata dagli altri connettori,
        # così i pruner riusabili le formattano senza sapere che è un grafo Neo4j
        for rel in rows[0].get("rels") or []:
            rel_type = rel.get("rel")
            if not rel_type:
                continue
            names = [n for n in (self._natural_name(t or {}) for t in rel.get("targets") or []) if n]
            if names:
                properties.setdefault(f"-[:{rel_type}]->", []).extend(names)

        return EntityData(
            id=entity_id,
            label=self._natural_name(props) or entity_id,
            description=", ".join(labels),
            properties=properties,
        )

    def _label_properties(self, label: str) -> list[dict[str, str]]:
        """Elenca le proprietà di una label con il loro tipo."""
        # Senza il tipo il modello scrive filtri assurdi come {released: true} su una
        # proprietà che contiene un anno, ottenendo zero righe da una query valida.
        try:
            rows = self._run(
                f"MATCH (n:`{label}`) WITH n LIMIT $sample "
                f"UNWIND keys(n) AS k "
                f"RETURN DISTINCT k AS prop, valueType(n[k]) AS type",
                {"sample": _SCHEMA_SAMPLE_SIZE},
            )
            return sorted(
                ({"name": r["prop"], "type": self._normalize_type(r.get("type"))} for r in rows if r.get("prop")),
                key=lambda p: p["name"],
            )
        except Exception:
            logger.debug("valueType() non disponibile per :%s, deduco il tipo da un campione", label)

        # valueType() esiste solo dalle versioni recenti di Neo4j 5
        try:
            rows = self._run(
                f"MATCH (n:`{label}`) WITH n LIMIT $sample "
                f"UNWIND keys(n) AS k "
                f"WITH k, head(collect(n[k])) AS sample "
                f"RETURN k AS prop, sample",
                {"sample": _SCHEMA_SAMPLE_SIZE},
            )
            return sorted(
                ({"name": r["prop"], "type": self._infer_type(r.get("sample"))} for r in rows if r.get("prop")),
                key=lambda p: p["name"],
            )
        except Exception as err:
            logger.warning("lettura proprietà della label '%s' fallita: %s", label, err)
            return []

    @staticmethod
    def _normalize_type(raw_type: Any) -> str:
        """Riduce il tipo di valueType() alla forma essenziale ('INTEGER NOT NULL' -> 'INTEGER')."""
        if not raw_type:
            return "UNKNOWN"
        return str(raw_type).replace(" NOT NULL", "").strip()

    @staticmethod
    def _infer_type(sample: Any) -> str:
        """Deduce il tipo di una proprietà da un valore campione."""
        if isinstance(sample, bool):
            return "BOOLEAN"
        if isinstance(sample, int):
            return "INTEGER"
        if isinstance(sample, float):
            return "FLOAT"
        if isinstance(sample, str):
            return "STRING"
        if isinstance(sample, (list, tuple)):
            return "LIST"
        return "UNKNOWN"

    def get_schema(self) -> dict[str, Any]:
        """Introspeziona label, proprietà e meta-grafo delle relazioni, con cache per istanza."""
        # lo schema non cambia durante l'esecuzione: rileggerlo a ogni domanda
        # costerebbe diversi round-trip inutili
        if self._schema_cache is not None:
            return self._schema_cache

        schema: dict[str, Any] = {"labels": {}, "relationships": []}
        try:
            for row in self._run("CALL db.labels() YIELD label RETURN label", {}):
                label = row.get("label")
                if label:
                    schema["labels"][label] = self._label_properties(label)

            rel_rows = self._run(
                "MATCH (a)-[r]->(b) "
                "RETURN DISTINCT labels(a)[0] AS from_label, type(r) AS rel_type, labels(b)[0] AS to_label",
                {},
            )
            schema["relationships"] = [
                {"from": r.get("from_label"), "type": r.get("rel_type"), "to": r.get("to_label")}
                for r in rel_rows
                if r.get("rel_type")
            ]
        except Exception as err:
            # senza schema il modello non saprebbe quali relazioni esistono
            raise KnowledgeGraphUnavailableError("neo4j", str(err)) from err

        self._schema_cache = schema
        return schema

    def _simplify_value(self, value: Any) -> Any:
        """Riduce nodi e liste al loro nome leggibile, lasciando intatti gli scalari."""
        if isinstance(value, dict):
            return self._natural_name(value) or value
        if isinstance(value, list):
            return [self._simplify_value(v) for v in value]
        return value

    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalizza i risultati: Cypher restituisce già valori leggibili, non URI da risolvere."""
        return [{key: self._simplify_value(value) for key, value in row.items()} for row in raw_results]
