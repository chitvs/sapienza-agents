from connectors.base_connector import BaseConnector
from grounders.base_grounder import BaseGrounder

class WikidataGrounder(BaseGrounder):

    def __init__(self, connector: BaseConnector):
        self.connector = connector

    def ground(self, raw_results: list[dict]) -> list[dict]:
        grounded_results = []

        for row in raw_results:
            grounded_row = {}
            for var_name, var_data in row.items():
                # gestisce sia dizionari grezzi dello SPARQLExecutor che valori stringa diretti
                val = var_data.get("value", "") if isinstance(var_data, dict) else str(var_data)

                # se il valore è un URI di Wikidata (es. http://www.wikidata.org/entity/Q937)
                if "wikidata.org/entity/Q" in val:
                    qid = val.split("/")[-1]
                    entity = self.connector.get_entity(qid)
                    grounded_row[var_name] = entity.label if entity else val
                else:
                    grounded_row[var_name] = val

            grounded_results.append(grounded_row)

        return grounded_results
