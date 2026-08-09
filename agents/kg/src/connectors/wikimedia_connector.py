import re
import time
import logging
import requests
from typing import Any
from connectors.base_connector import (
    BaseConnector,
    EntityCandidate,
    EntityData,
    EntityReference,
    KnowledgeGraphUnavailableError,
)

logger = logging.getLogger(__name__)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# forma degli uri con cui l'endpoint restituisce i riferimenti a entità
WIKIDATA_ENTITY_NS = "wikidata.org/entity/Q"

_ISO_DATETIME = re.compile(r"^[+-]?\d{4,}-\d{2}-\d{2}T[\d:]+Z$")

class WikimediaConnector(BaseConnector):
    """Connettore verso le API REST di Wikidata, con cache in-memory e richieste batch."""

    entity_prefix = "wd:"
    property_prefix = "wdt:"

    def __init__(self, language: str = "en", max_cache_size: int = 1000):
        self.language = language
        self.max_cache_size = max_cache_size
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent/1.0 (https://github.com/chitvs/sapienza-agents)",
            "Accept": "application/json",
        })
        self._property_label_cache: dict[str, tuple[str, bool]] = {}
        self._entity_cache: dict[str, EntityData] = {}
        self._search_cache: dict[str, list[EntityCandidate]] = {}

    def _set_cache_entry(self, cache_dict: dict, key: str, value: Any) -> None:
        """Memorizza un elemento in cache rispettando il limite massimo."""
        if len(cache_dict) >= self.max_cache_size and key not in cache_dict:
            first_key = next(iter(cache_dict))
            del cache_dict[first_key]
        cache_dict[key] = value

    def _get_with_retry(self, params: dict[str, str]) -> requests.Response:
        """Esegue una GET con retry e backoff in caso di rate limiting (HTTP 429)."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                time.sleep(0.15)
                response = self.session.get(WIKIDATA_API, params=params)
                if response.status_code == 429:
                    logger.info("rate limit 429 incontrato, attesa %d s...", 3 * (attempt + 1))
                    time.sleep(3.0 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response
            except requests.HTTPError as err:
                if err.response is not None and err.response.status_code == 429 and attempt < max_retries - 1:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                raise err
            except requests.RequestException:
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise

        raise requests.HTTPError("Numero massimo di tentativi superato per rate limit 429")

    def _extract_multilingual_text(self, text_dict: dict[str, dict[str, str]]) -> str:
        """Estrae il testo nella lingua richiesta, con fallback sulle altre disponibili."""
        if not text_dict:
            return ""
        values = []
        if self.language in text_dict:
            val = text_dict[self.language].get("value", "").strip()
            if val:
                values.append(val)
        for lang_info in text_dict.values():
            val = lang_info.get("value", "").strip()
            if val and val not in values:
                values.append(val)
        return " / ".join(values)

    def _fetch_property_labels(self, prop_ids: list[str]) -> dict[str, tuple[str, bool]]:
        """Recupera etichette e tipo (statement o identificatore) delle proprietà Wikidata."""
        missing = [p for p in prop_ids if p not in self._property_label_cache]
        if not missing:
            return {p: self._property_label_cache[p] for p in prop_ids}

        for i in range(0, len(missing), 50):
            batch = missing[i:i+50]
            params = {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|datatype",
                "languages": self.language,
                "format": "json",
            }
            try:
                res = self._get_with_retry(params).json()
                entities = res.get("entities", {})
                for pid, data in entities.items():
                    labels = data.get("labels", {})
                    datatype = data.get("datatype", "")
                    is_identifier = (datatype == "external-id")
                    label_str = self._extract_multilingual_text(labels) or pid
                    self._set_cache_entry(self._property_label_cache, pid, (label_str, is_identifier))
            except Exception as err:
                logger.warning("recupero etichette proprietà fallito: %s", err)
                for pid in batch:
                    self._set_cache_entry(self._property_label_cache, pid, (pid, False))

        return {p: self._property_label_cache.get(p, (p, False)) for p in prop_ids}

    def search_entity(self, text: str, limit: int = 5, language: str | None = None) -> list[EntityCandidate]:
        """Cerca entità su Wikidata a partire dal testo di una menzione."""
        search_lang = language or self.language
        cache_key = f"{text.strip().lower()}:{limit}:{search_lang}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": search_lang,
            "uselang": search_lang,
            "format": "json",
            "limit": limit,
        }
        results = []
        try:
            response = self._get_with_retry(params)
            data = response.json()
            if "search" in data:
                for item in data["search"]:
                    entity_id = item["id"]
                    label = item.get("label", "")
                    description = item.get("description", "")
                    results.append(EntityCandidate(id=entity_id, label=label, description=description))
        except Exception as err:
            # senza candidati la pipeline procederebbe senza entità ancorate,
            # producendo una query inventata invece di un errore
            raise KnowledgeGraphUnavailableError("wikidata", str(err)) from err

        self._set_cache_entry(self._search_cache, cache_key, results)
        return results

    def get_entities(self, entity_ids: list[str]) -> dict[str, EntityData]:
        """Recupera più entità in un'unica richiesta batch invece di una chiamata per entità."""
        results = {}
        missing_ids = []

        for eid in entity_ids:
            cache_key = f"{eid}:{self.language}"
            if cache_key in self._entity_cache:
                results[eid] = self._entity_cache[cache_key]
            else:
                missing_ids.append(eid)

        if not missing_ids:
            return results

        for i in range(0, len(missing_ids), 50):
            batch = missing_ids[i:i+50]
            params = {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "languages": self.language,
                "props": "labels|descriptions|claims",
                "format": "json",
            }
            try:
                response = self._get_with_retry(params)
                data = response.json()
                entities = data.get("entities", {})

                # le proprietà di tutte le entità si raccolgono insieme per risolverne le etichette in un colpo solo
                all_raw_props = {}
                for eid in batch:
                    ent_data = entities.get(eid, {})
                    raw_properties = {}
                    if "claims" in ent_data:
                        for prop_id, claims_list in ent_data["claims"].items():
                            values = []
                            for claim in claims_list:
                                if "mainsnak" in claim and "datavalue" in claim["mainsnak"]:
                                    if "value" in claim["mainsnak"]["datavalue"]:
                                        val = claim["mainsnak"]["datavalue"]["value"]
                                        if isinstance(val, dict):
                                            if "id" in val:
                                                values.append(EntityReference(id=val["id"]))
                                            elif "time" in val:
                                                raw_time = str(val["time"]).lstrip("+")
                                                date_part = raw_time.split("T")[0]
                                                values.append(date_part)
                                            elif "amount" in val:
                                                values.append(str(val["amount"]).lstrip("+"))
                                        elif isinstance(val, str):
                                            values.append(val)
                            if values:
                                raw_properties[prop_id] = values
                    all_raw_props[eid] = raw_properties

                all_prop_ids = list({pid for props in all_raw_props.values() for pid in props})
                prop_meta = self._fetch_property_labels(all_prop_ids)

                for eid in batch:
                    ent_data = entities.get(eid, {})
                    label = self._extract_multilingual_text(ent_data.get("labels", {})) or eid
                    description = self._extract_multilingual_text(ent_data.get("descriptions", {}))
                    raw_props = all_raw_props.get(eid, {})

                    properties = {}
                    for prop_id, vals in raw_props.items():
                        label_text, is_identifier = prop_meta.get(prop_id, (prop_id, False))
                        prefix = "[ID] " if is_identifier else ""
                        key_name = f"{prop_id} {prefix}({label_text})" if label_text and label_text != prop_id else prop_id
                        properties[key_name] = vals

                    entity_res = EntityData(id=eid, label=label, description=description, properties=properties)
                    cache_key = f"{eid}:{self.language}"
                    self._set_cache_entry(self._entity_cache, cache_key, entity_res)
                    results[eid] = entity_res

            except Exception as err:
                # un fallback vuoto sarebbe indistinguibile da un'entità priva di fatti,
                # e il modello genererebbe una query non ancorata allo schema reale
                raise KnowledgeGraphUnavailableError("wikidata", str(err)) from err

        return results

    def get_entity(self, entity_id: str) -> EntityData:
        """Recupera i dati completi di una singola entità."""
        res = self.get_entities([entity_id])
        return res.get(entity_id, EntityData(id=entity_id, label=entity_id, description="", properties={}))

    def looks_like_entity_id(self, value: str) -> bool:
        """Su Wikidata i riferimenti a entità sono QID nella forma Q seguita da cifre."""
        return bool(re.match(r"^Q\d+$", str(value)))

    def is_valid_candidate(self, candidate: EntityCandidate) -> bool:
        """Accetta solo QID ben formati, escludendo disambigue e categorie Wikimedia."""
        cid = str(getattr(candidate, "id", "") or "")
        if not re.match(r"^Q\d+$", cid):
            return False

        desc = (getattr(candidate, "description", "") or "").lower()
        junk_markers = ("disambiguation", "wikimedia category", "categoria wikimedia")
        return not any(marker in desc for marker in junk_markers)

    @staticmethod
    def _extract_value(var_data: Any) -> str:
        if isinstance(var_data, dict):
            return var_data.get("value", "")
        return str(var_data)

    def ground_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Risolve gli id grezzi in etichette leggibili con un'unica richiesta batch."""
        entity_ids: set[str] = set()
        for row in raw_results:
            for var_data in row.values():
                val = self._extract_value(var_data)
                if WIKIDATA_ENTITY_NS in val:
                    entity_ids.add(val.split("/")[-1])

        resolved_labels: dict[str, str] = {}
        if entity_ids:
            entities = self.get_entities(list(entity_ids))
            for entity_id, entity_data in entities.items():
                resolved_labels[entity_id] = entity_data.label if entity_data and entity_data.label else entity_id

        grounded_results = []
        for row in raw_results:
            grounded_row: dict[str, Any] = {}
            sources: dict[str, str] = {}
            for var_name, var_data in row.items():
                val = self._extract_value(var_data)

                # il valore è un riferimento a un'entità, non un letterale
                if WIKIDATA_ENTITY_NS in val:
                    entity_id = val.split("/")[-1]
                    grounded_row[var_name] = resolved_labels.get(entity_id, val)
                    # l'uri originale si conserva a parte: permette all'interfaccia di
                    # rendere il valore un link verificabile alla fonte
                    sources[var_name] = val
                elif _ISO_DATETIME.match(val):
                    # +1879-03-14T00:00:00Z -> 1879-03-14, tenendo il segno degli anni a.C.
                    grounded_row[var_name] = val.lstrip("+").split("T")[0]
                else:
                    grounded_row[var_name] = val

            if sources:
                grounded_row["_sources"] = sources
            grounded_results.append(grounded_row)
        return grounded_results
