import requests
from connectors.base_connector import BaseConnector, EntityCandidate, EntityData

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

class WikimediaConnector(BaseConnector):
    """Connettore verso Wikidata."""

    def __init__(self, language: str = "en"): 
        # todo: aggiungi altre lingue?
        # per ora il test è solo sull'inglese (Q1 universe)
        self.language = language
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "kg-agent",
            "Accept": "application/json",
        })

    # ricerca (testo -> ID)
    def search_entity(self, text: str, limit: int = 5) -> list[EntityCandidate]:
        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": self.language,
            "format": "json",
            "limit": limit,
        }
        response = self.session.get(WIKIDATA_API, params=params)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        # la chiave search esiste?
        if "search" in data:
            for item in data["search"]:
                entity_id = item["id"]
                
                # label?
                label = ""
                if "label" in item:
                    label = item["label"]
                    
                # creazione oggetto e aggiunta alla lista
                # todo: aggiungi descrizione
                candidate = EntityCandidate(id=entity_id, label=label)
                results.append(candidate)
                
        return results

    # estrazione (ID -> grafo)
    def get_entity(self, entity_id: str) -> EntityData:
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "languages": self.language,
            "props": "labels|claims",
            "format": "json",
        }
        response = self.session.get(WIKIDATA_API, params=params)
        response.raise_for_status()
        
        data = response.json()

        # estrazione dell'entità
        entity = {}
        if "entities" in data:
            if entity_id in data["entities"]:
                entity = data["entities"][entity_id]

        # estrazione della label
        label = ""
        if "labels" in entity:
            if self.language in entity["labels"]:
                if "value" in entity["labels"][self.language]:
                    label = entity["labels"][self.language]["value"]

        # estrazione delle properties, scavando in profondità il json che ci ha risposto wikimedia
        properties = {}
        if "claims" in entity:
            for prop_id, claims_list in entity["claims"].items():
                values = []
                
                for claim in claims_list:

                    if "mainsnak" in claim:
                        if "datavalue" in claim["mainsnak"]:
                            if "value" in claim["mainsnak"]["datavalue"]:
                                val = claim["mainsnak"]["datavalue"]["value"]
                                
                                # controllo di che tipo è il valore
                                if isinstance(val, dict):
                                    if "id" in val:
                                        values.append(val["id"])
                                elif isinstance(val, str):
                                    values.append(val)
                
                # se ci sono dei valori li salviamo
                if len(values) > 0:
                    properties[prop_id] = values

        return EntityData(id=entity_id, label=label, properties=properties)
