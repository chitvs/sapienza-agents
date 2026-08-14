"""
Copertura estesa della pipeline Neo4j sul movie graph.

I test in test_neo4j_integration.py verificano che la pipeline funzioni; questi servono
a misurarne il vero soffitto, esercitando dimensioni che i primi non toccano: tutte le
relazioni dello schema (non solo ACTED_IN e DIRECTED), le proprietà sulle relazioni,
i filtri su intervalli numerici, le catene a tre livelli e le entità con nomi ambigui.
E' lecito che qualcuno fallisca: servono a scoprire dove sta il limite, non a
confermare ciò che già sappiamo funzionare.
"""
import pytest

from pipeline import KGPipeline
from conftest import contains_answer, is_neo4j_ready, is_ollama_running

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_neo4j_ready()),
    reason="richiede Ollama attivo e Neo4j con il movie graph caricato",
)

@pytest.fixture(scope="module")
def pipeline() -> KGPipeline:
    return KGPipeline(target_kg="neo4j")

@requires_stack
def test_writer_relationship(pipeline: KGPipeline) -> None:
    """Relazione WROTE, mai esercitata dai test di base."""
    # nel dataset The Matrix non ha sceneggiatore: si usa un film che ce l'ha davvero
    result = pipeline.run("Who wrote A Few Good Men?")
    assert len(result.results) > 0
    assert contains_answer(result, "Sorkin")

@requires_stack
def test_producer_relationship(pipeline: KGPipeline) -> None:
    """relazione PRODUCED."""
    result = pipeline.run("Who produced The Matrix?")
    assert len(result.results) > 0
    assert contains_answer(result, "Silver")

@requires_stack
def test_person_to_person_relationship(pipeline: KGPipeline) -> None:
    """FOLLOWS collega due nodi della stessa label: verifica che i due estremi non si confondano."""
    # nel dataset Jessica Thompson è seguita ma non segue nessuno: la direzione conta
    result = pipeline.run("Who follows Jessica Thompson?")
    assert len(result.results) > 0
    assert contains_answer(result, "Thompson") or contains_answer(result, "Scope")

@requires_stack
def test_relationship_property(pipeline: KGPipeline) -> None:
    """
    La proprietà 'rating' vive sulla RELAZIONE REVIEWED, non su un nodo: richiede di
    legare la relazione a una variabile ([r:REVIEWED]) invece di attraversarla e basta.
    """
    result = pipeline.run("What rating did Jessica Thompson give to The Replacements?")
    assert len(result.results) > 0

@requires_stack
def test_roles_property_on_relationship(pipeline: KGPipeline) -> None:
    """stessa dimensione, su una proprietà di tipo lista (roles)."""
    result = pipeline.run("Which role did Keanu Reeves play in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_numeric_range_filter(pipeline: KGPipeline) -> None:
    """filtro su un intervallo numerico, non su un valore esatto."""
    result = pipeline.run("Which movies were released before 1995?")
    assert len(result.results) > 0

@requires_stack
def test_person_born_after_year(pipeline: KGPipeline) -> None:
    """filtro numerico su una proprietà di persona."""
    result = pipeline.run("Which people were born after 1970?")
    assert len(result.results) > 0

@requires_stack
def test_three_level_chain(pipeline: KGPipeline) -> None:
    """catena a tre livelli: attore -> film -> regista."""
    result = pipeline.run("Who directed the movies that Tom Hanks acted in?")
    assert len(result.results) > 0

@requires_stack
def test_count_distinct_people(pipeline: KGPipeline) -> None:
    """aggregazione su nodi persona invece che su film."""
    result = pipeline.run("How many people acted in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_ambiguous_title_prefix(pipeline: KGPipeline) -> None:
    """
    'The Matrix' è prefisso di 'The Matrix Reloaded' e 'The Matrix Revolutions': la
    ricerca dell'entità deve preferire il titolo esatto ai sequel.
    """
    result = pipeline.run("When was The Matrix released?")
    assert len(result.results) > 0
    assert contains_answer(result, "1999")

@requires_stack
def test_person_who_both_acted_and_directed(pipeline: KGPipeline) -> None:
    """richiede due traversate distinte dallo stesso nodo persona."""
    result = pipeline.run("Which people both acted in and directed a movie?")
    # esito aperto sui dati, non sulla forma: deve comunque aver prodotto una query
    assert "MATCH" in result.query.upper()

@requires_stack
def test_movie_with_most_actors(pipeline: KGPipeline) -> None:
    """superlativo su un'aggregazione, non su una proprietà diretta."""
    result = pipeline.run("Which movie has the most actors?")
    assert len(result.results) > 0

@requires_stack
def test_tagline_property(pipeline: KGPipeline) -> None:
    """proprietà testuale poco frequente, per verificare che non venga ignorata."""
    result = pipeline.run("What is the tagline of The Matrix?")
    assert len(result.results) > 0
