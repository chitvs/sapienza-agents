from connectors.wikimedia_connector import WikimediaConnector
from grounders.base_grounder import BaseGrounder
from grounders.wikidata_grounder import WikidataGrounder

def test_wikidata_grounder_inheritance():
    connector = WikimediaConnector()
    grounder = WikidataGrounder(connector=connector)
    assert isinstance(grounder, BaseGrounder)

def test_wikidata_grounder_resolution():
    connector = WikimediaConnector()
    grounder = WikidataGrounder(connector=connector)

    raw_results = [
        {
            "person": {"value": "http://www.wikidata.org/entity/Q937"},
            "dob": {"value": "1879-03-14T00:00:00Z"},
        }
    ]

    results = grounder.ground(raw_results)

    assert len(results) == 1
    assert results[0]["person"] == "Albert Einstein"
    assert results[0]["dob"] == "1879-03-14T00:00:00Z"
