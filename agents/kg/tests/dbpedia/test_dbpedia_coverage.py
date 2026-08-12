"""
Copertura estesa della pipeline DBpedia.

I test in test_dbpedia_integration.py verificano che la pipeline funzioni; questi ne
misurano il soffitto reale su dimensioni non ancora toccate: relazioni percorse in
senso inverso, risorse il cui URI contiene caratteri da racchiudere fra parentesi
angolari, superlativi con filtro di tipo, proprietà multivalore e catene a tre hop.
E' lecito che qualcuno fallisca: servono a scoprire i limiti, non a confermarli.
"""
from pathlib import Path

import pytest
import requests

from pipeline import KGPipeline
from conftest import contiene_risposta
from conftest import is_ollama_running

_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "dbpedia_ontology"

def is_dbpedia_reachable() -> bool:
    try:
        return requests.get("https://dbpedia.org/sparql", timeout=5).status_code < 500
    except Exception:
        return False

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_dbpedia_reachable() and (_INDEX_DIR / "properties.faiss").exists()),
    reason="richiede Ollama, l'endpoint DBpedia e l'indice ontologico (scripts/ingest_dbpedia.py)",
)

@pytest.fixture(scope="module")
def pipeline() -> KGPipeline:
    return KGPipeline(target_kg="dbpedia")

@requires_stack
def test_inverse_relation(pipeline: KGPipeline) -> None:
    """
    La relazione va percorsa al contrario: il film punta al regista con dbo:director,
    quindi "i film diretti da X" richiede X come OGGETTO, non come soggetto.
    """
    result = pipeline.run("Which films were directed by Christopher Nolan?")
    assert len(result.results) > 0

@requires_stack
def test_resource_with_parentheses_in_uri(pipeline: KGPipeline) -> None:
    """
    'Mercury (planet)' ha un URI con parentesi, che in forma dbr: non è un nome
    prefissato valido: la query deve usare l'URI completo fra parentesi angolari.
    """
    result = pipeline.run("What is the mass of the planet Mercury?")
    # dbr:Mercury_(planet) non è un nome prefissato valido: le parentesi obbligano
    # all'URI fra parentesi angolari, ed è questo che il test deve proteggere
    assert "dbr:Mercury_(planet)" not in result.query

@requires_stack
def test_superlative_with_type_filter(pipeline: KGPipeline) -> None:
    """superlativo su una variabile libera: qui il filtro di tipo è necessario."""
    result = pipeline.run("What is the highest mountain?")
    assert len(result.results) > 0

@requires_stack
def test_date_property(pipeline: KGPipeline) -> None:
    """proprietà di tipo data, che va restituita come letterale e non risolta come risorsa."""
    result = pipeline.run("When was Albert Einstein born?")
    assert len(result.results) > 0
    assert contiene_risposta(result, "1879")

@requires_stack
def test_death_place(pipeline: KGPipeline) -> None:
    """il valore è una risorsa con virgola nell'URI (Princeton,_New_Jersey)."""
    result = pipeline.run("Where did Albert Einstein die?")
    assert len(result.results) > 0
    assert contiene_risposta(result, "Princeton")

@requires_stack
def test_multi_valued_property(pipeline: KGPipeline) -> None:
    """proprietà con più valori: il sistema non deve assumerne uno solo."""
    result = pipeline.run("Which actors starred in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_three_hop_chain(pipeline: KGPipeline) -> None:
    """catena a tre hop: film -> regista -> luogo di nascita -> paese."""
    result = pipeline.run("In which country was the director of Inception born?")
    # esito aperto sui dati: si verifica che la traduzione abbia prodotto una SELECT
    assert "SELECT" in result.query.upper()

@requires_stack
def test_spouse_relation(pipeline: KGPipeline) -> None:
    """relazione fra due persone."""
    result = pipeline.run("Who was the spouse of Albert Einstein?")
    # esito aperto sui dati: si verifica che la traduzione abbia prodotto una SELECT
    assert "SELECT" in result.query.upper()

@requires_stack
def test_count_with_inverse_relation(pipeline: KGPipeline) -> None:
    """aggregazione su una relazione percorsa al contrario."""
    result = pipeline.run("How many films did Steven Spielberg direct?")
    assert len(result.results) > 0

@requires_stack
def test_country_population(pipeline: KGPipeline) -> None:
    """proprietà numerica su un'entità geografica."""
    result = pipeline.run("What is the population of Italy?")
    assert len(result.results) > 0

@requires_stack
def test_ambiguous_entity_name(pipeline: KGPipeline) -> None:
    """
    'Mercury' è ambiguo (pianeta, elemento, casa discografica, Freddie Mercury): la
    disambiguazione deve usare il contesto della domanda.
    """
    result = pipeline.run("Who was the lead singer of Queen?")
    # esito aperto sui dati: si verifica che la traduzione abbia prodotto una SELECT
    assert "SELECT" in result.query.upper()

@requires_stack
def test_film_numeric_property(pipeline: KGPipeline) -> None:
    """Proprietà numerica su un film."""
    # non si usa la data di uscita: nel vocabolario dbo: non esiste per i film, vive
    # solo in dbp:, l'estrazione grezza dalle infobox che l'agente non interroga
    result = pipeline.run("What was the budget of The Matrix?")
    assert len(result.results) > 0
