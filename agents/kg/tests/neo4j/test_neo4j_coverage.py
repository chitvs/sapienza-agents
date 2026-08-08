"""
Copertura estesa della pipeline Neo4j sul movie graph.

I test in test_neo4j_integration.py verificano che la pipeline funzioni; questi servono
a misurarne il vero soffitto, esercitando dimensioni che i primi non toccano: tutte le
relazioni dello schema (non solo ACTED_IN e DIRECTED), le proprieta' sulle relazioni,
i filtri su intervalli numerici, le catene a tre livelli e le entita' con nomi ambigui.
E' lecito che qualcuno fallisca: servono a scoprire dove sta il limite, non a
confermare cio' che gia' sappiamo funzionare.
"""
import pytest
import requests

from pipeline import KGPipeline

def is_ollama_running() -> bool:
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

def is_neo4j_ready() -> bool:
    try:
        from configs.settings import settings
        from executors.cypher_executor import CypherExecutor

        executor = CypherExecutor(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            timeout=5.0,
        )
        rows = executor.run_internal("MATCH (m:Movie) RETURN count(m) AS c", {})
        executor.close()
        return bool(rows) and rows[0].get("c", 0) > 0
    except Exception:
        return False

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
    assert any("Sorkin" in str(row) for row in result.results)

@requires_stack
def test_producer_relationship(pipeline: KGPipeline) -> None:
    """relazione PRODUCED."""
    result = pipeline.run("Who produced The Matrix?")
    assert len(result.results) > 0
    assert any("Silver" in str(row) for row in result.results)

@requires_stack
def test_person_to_person_relationship(pipeline: KGPipeline) -> None:
    """FOLLOWS collega due nodi della stessa label: verifica che i due estremi non si confondano."""
    # nel dataset Jessica Thompson è seguita ma non segue nessuno: la direzione conta
    result = pipeline.run("Who follows Jessica Thompson?")
    assert len(result.results) > 0
    assert any("Thompson" in str(row) or "Scope" in str(row) for row in result.results)

@requires_stack
def test_relationship_property(pipeline: KGPipeline) -> None:
    """
    La proprieta' 'rating' vive sulla RELAZIONE REVIEWED, non su un nodo: richiede di
    legare la relazione a una variabile ([r:REVIEWED]) invece di attraversarla e basta.
    """
    result = pipeline.run("What rating did Jessica Thompson give to The Replacements?")
    assert len(result.results) > 0

@requires_stack
def test_roles_property_on_relationship(pipeline: KGPipeline) -> None:
    """stessa dimensione, su una proprieta' di tipo lista (roles)."""
    result = pipeline.run("Which role did Keanu Reeves play in The Matrix?")
    assert len(result.results) > 0

@requires_stack
def test_numeric_range_filter(pipeline: KGPipeline) -> None:
    """filtro su un intervallo numerico, non su un valore esatto."""
    result = pipeline.run("Which movies were released before 1995?")
    assert len(result.results) > 0

@requires_stack
def test_person_born_after_year(pipeline: KGPipeline) -> None:
    """filtro numerico su una proprieta' di persona."""
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
    'The Matrix' e' prefisso di 'The Matrix Reloaded' e 'The Matrix Revolutions': la
    ricerca dell'entita' deve preferire il titolo esatto ai sequel.
    """
    result = pipeline.run("When was The Matrix released?")
    assert len(result.results) > 0
    assert any("1999" in str(row) for row in result.results)

@requires_stack
def test_person_who_both_acted_and_directed(pipeline: KGPipeline) -> None:
    """richiede due traversate distinte dallo stesso nodo persona."""
    result = pipeline.run("Which people both acted in and directed a movie?")
    assert len(result.results) >= 0  # esito aperto: interessa che non sollevi

@requires_stack
def test_movie_with_most_actors(pipeline: KGPipeline) -> None:
    """superlativo su un'aggregazione, non su una proprieta' diretta."""
    result = pipeline.run("Which movie has the most actors?")
    assert len(result.results) > 0

@requires_stack
def test_tagline_property(pipeline: KGPipeline) -> None:
    """proprieta' testuale poco frequente, per verificare che non venga ignorata."""
    result = pipeline.run("What is the tagline of The Matrix?")
    assert len(result.results) > 0
