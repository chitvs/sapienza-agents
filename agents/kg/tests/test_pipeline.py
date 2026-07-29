import pytest
import requests

from connectors.wikimedia_connector import WikimediaConnector
from linkers.llm_linker import LLMLinker
from translators.sparql_translator import SPARQLTranslator
from executors.sparql_executor import SPARQLExecutor
from grounders.wikidata_grounder import WikidataGrounder
from pipeline import KGPipeline

# test pipeline totale con LLMLinker
# todo: generalizzare (json) e API

def is_ollama_running():
    try:
        res = requests.get("http://localhost:11434/", timeout=1.0)
        return res.status_code == 200
    except requests.exceptions.RequestException:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo su http://localhost:11434")
def test_pipeline_end_to_end():
    connector = WikimediaConnector()
    linker = LLMLinker(connector=connector, model_name="llama3.2")
    translator = SPARQLTranslator(model_name="llama3.2")
    executor = SPARQLExecutor()
    grounder = WikidataGrounder(connector=connector)

    pipeline = KGPipeline(
        connector=connector,
        linker=linker,
        translator=translator,
        executor=executor,
        grounder=grounder,
    )

    question = "Qual è la data di nascita di Albert Einstein?"
    results = pipeline.run(question)

    assert isinstance(results, list)
    assert len(results) > 0
    first_row_values = str(results[0])
    assert "1879-03-14" in first_row_values
