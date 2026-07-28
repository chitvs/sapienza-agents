from connectors.wikimedia_connector import WikimediaConnector
from linkers.base_linker import BaseLinker, LinkedEntity

class LookupLinker(BaseLinker):
    """Linker basato sulla ricerca diretta di Wikidata, restituisce banalmente il primo risultato."""

    def __init__(self, connector: WikimediaConnector | None = None):
        self.connector = connector or WikimediaConnector()

    def link(self, text: str) -> list[LinkedEntity]:
        candidates = self.connector.search_entity(text, limit=1) # limite=1 e quindi il primo risultato
        if not candidates:
            return []

        best_match = candidates[0]

        return [
            LinkedEntity(
                mention=text,
                qid=best_match.id,
                label=best_match.label or text,
            )
        ]
