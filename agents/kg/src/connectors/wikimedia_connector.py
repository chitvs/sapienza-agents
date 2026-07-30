import time
import requests
from connectors.base_connector import BaseConnector, EntityCandidate, EntityData

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

class WikimediaConnector(BaseConnector):
    """connettore verso Wikidata."""

    def __init__(self, language: str = "en"):
        self.language = language
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent",
            "Accept": "application/json",
        })

    def _get_with_retry(self, params: dict[str, str]) -> requests.Response:
        """esegue richieste GET con retry automatico in caso di rate limiting (HTTP 429)."""
        max_retries = 3
        for attempt in range(max_retries):
            response = self.session.get(WIKIDATA_API, params=params)
            if response.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        response.raise_for_status()
        return response

    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": self.language,
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
                    candidate = EntityCandidate(id=entity_id, label=label, description=description)
                    results.append(candidate)

            return results
        except Exception:
            return [EntityCandidate(id=text, label=text)]

    def get_entity(self, entity_id: str) -> EntityData:
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "languages": self.language,
            "props": "labels|claims",
            "format": "json",
        }
        try:
            response = self._get_with_retry(params)
            data = response.json()
            entity = {}
            if "entities" in data and entity_id in data["entities"]:
                entity = data["entities"][entity_id]

            label = ""
            if "labels" in entity and self.language in entity["labels"]:
                label = entity["labels"][self.language].get("value", "")

            properties = {}
            if "claims" in entity:
                for prop_id, claims_list in entity["claims"].items():
                    values = []
                    for claim in claims_list:
                        if "mainsnak" in claim and "datavalue" in claim["mainsnak"]:
                            if "value" in claim["mainsnak"]["datavalue"]:
                                val = claim["mainsnak"]["datavalue"]["value"]
                                if isinstance(val, dict) and "id" in val:
                                    values.append(val["id"])
                                elif isinstance(val, str):
                                    values.append(val)

                    if values:
                        properties[prop_id] = values

            return EntityData(id=entity_id, label=label, properties=properties)
        except Exception:
            return EntityData(id=entity_id, label=entity_id, properties={})
