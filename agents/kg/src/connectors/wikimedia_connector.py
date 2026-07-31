import time
import logging
import requests
from connectors.base_connector import BaseConnector, EntityCandidate, EntityData

logger = logging.getLogger(__name__)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

CORE_PROPERTIES = {
    "P31", "P279", "P36", "P106", "P569", "P570", "P19", "P20", "P17", "P131",
    "P27", "P108", "P69", "P463", "P35", "P6", "P39", "P50", "P57", "P161",
    "P61", "P580", "P582", "P102", "P1376", "P735", "P734"
}

class WikimediaConnector(BaseConnector):
    """connettore verso wikidata api rest multilingua con caching in-memory."""

    def __init__(self, language: str = "en"):
        self.language = language
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent",
            "Accept": "application/json",
        })
        self._property_label_cache: dict[str, str] = {}
        self._entity_cache: dict[str, EntityData] = {}
        self._search_cache: dict[str, list[EntityCandidate]] = {}

    def _get_with_retry(self, params: dict[str, str]) -> requests.Response:
        """esegue richieste get con retry automatico e backoff in caso di rate limiting (HTTP 429)."""
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

    def _fetch_property_labels(self, prop_ids: list[str]) -> dict[str, str]:
        """recupera le etichette delle proprietà wikidata in un'unica chiamata batch HTTP."""
        missing = [p for p in prop_ids if p not in self._property_label_cache]
        if not missing:
            return {p: self._property_label_cache[p] for p in prop_ids}

        for i in range(0, len(missing), 50):
            batch = missing[i:i+50]
            params = {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels",
                "languages": f"{self.language},en,it",
                "format": "json",
            }
            try:
                res = self._get_with_retry(params).json()
                entities = res.get("entities", {})
                for pid, data in entities.items():
                    labels = data.get("labels", {})
                    label_val = ""
                    for lang in [self.language, "en", "it"]:
                        if lang in labels:
                            label_val = labels[lang].get("value", "")
                            if label_val:
                                break
                    self._property_label_cache[pid] = label_val or pid
            except Exception as err:
                logger.warning("recupero etichette proprietà fallito: %s", err)
                for pid in batch:
                    self._property_label_cache[pid] = pid

        return {p: self._property_label_cache.get(p, p) for p in prop_ids}

    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        """cerca entità su wikidata sfruttando la cache in-memory."""
        cache_key = f"{text.strip().lower()}:{limit}:{self.language}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": self.language,
            "uselang": self.language,
            "format": "json",
            "limit": limit,
        }
        try:
            response = self._get_with_retry(params)
            data = response.json()
            results = []
            if "search" in data:
                for item in data["search"]:
                    entity_id = item["id"]
                    label = item.get("label", "")
                    description = item.get("description", "")
                    results.append(EntityCandidate(id=entity_id, label=label, description=description))

            self._search_cache[cache_key] = results
            return results
        except Exception as err:
            logger.warning("ricerca entità wikidata fallita per '%s': %s", text, err)
            return []

    def get_entity(self, entity_id: str) -> EntityData:
        """recupera i dati dell'entità sfruttando la cache in-memory."""
        cache_key = f"{entity_id}:{self.language}"
        if cache_key in self._entity_cache:
            return self._entity_cache[cache_key]

        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "languages": f"{self.language},en,it",
            "props": "labels|descriptions|claims",
            "format": "json",
        }
        try:
            response = self._get_with_retry(params)
            data = response.json()
            entity = {}
            if "entities" in data and entity_id in data["entities"]:
                entity = data["entities"][entity_id]

            label = ""
            if "labels" in entity:
                for lang in [self.language, "en", "it"]:
                    if lang in entity["labels"]:
                        label = entity["labels"][lang].get("value", "")
                        if label:
                            break

            description = ""
            if "descriptions" in entity:
                for lang in [self.language, "en", "it"]:
                    if lang in entity["descriptions"]:
                        description = entity["descriptions"][lang].get("value", "")
                        if description:
                            break

            raw_properties = {}
            if "claims" in entity:
                for prop_id, claims_list in entity["claims"].items():
                    values = []
                    for claim in claims_list:
                        if "mainsnak" in claim and "datavalue" in claim["mainsnak"]:
                            if "value" in claim["mainsnak"]["datavalue"]:
                                val = claim["mainsnak"]["datavalue"]["value"]
                                if isinstance(val, dict):
                                    if "id" in val:
                                        values.append(val["id"])
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

            # Ordina le proprietà per prioritizzare le proprietà fondamentali e i valori semantici PRIMA del troncamento a 40
            def prop_sorter(pid: str):
                is_core = 0 if pid in CORE_PROPERTIES else 1
                vals = raw_properties.get(pid, [])
                has_semantic_val = 0 if any(str(v).startswith("Q") or "-" in str(v) for v in vals) else 1
                return (is_core, has_semantic_val, pid)

            sorted_pids = sorted(raw_properties.keys(), key=prop_sorter)
            top_prop_ids = sorted_pids[:40]
            prop_labels = self._fetch_property_labels(top_prop_ids)

            properties = {}
            for prop_id in top_prop_ids:
                vals = raw_properties[prop_id]
                label_text = prop_labels.get(prop_id, prop_id)
                key_name = f"{prop_id} ({label_text})" if label_text and label_text != prop_id else prop_id
                properties[key_name] = vals

            result = EntityData(id=entity_id, label=label, description=description, properties=properties)
            self._entity_cache[cache_key] = result
            return result
        except Exception as err:
            logger.warning("recupero entità wikidata fallito per '%s': %s", entity_id, err)
            fallback = EntityData(id=entity_id, label=entity_id, description="", properties={})
            return fallback
