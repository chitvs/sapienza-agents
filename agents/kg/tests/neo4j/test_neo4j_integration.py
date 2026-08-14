"""
Test di integrazione end-to-end sul knowledge graph Neo4j (dominio cinema).

Richiedono due cose attive: un'istanza Neo4j con il movie graph ufficiale caricato
(vedi scripts/setup_neo4j_movies.py) e Ollama. Se manca una delle due, i test vengono
saltati invece di fallire, così la suite resta eseguibile anche su una macchina che
sta lavorando solo su Wikidata.

Le domande coprono le stesse dimensioni di complessità già verificate su Wikidata:
traversata diretta, traversata contro la direzione della relazione, catena a due hop,
aggregazione e superlativo.
"""
import pytest

from pipeline import KGPipeline
from conftest import contains_answer
from conftest import is_ollama_running

def is_neo4j_ready() -> bool:
    """verifica che neo4j risponda e che il movie graph sia effettivamente caricato."""
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
        rows = executor.execute_trusted("MATCH (m:Movie) RETURN count(m) AS c", {})
        executor.close()
        return bool(rows) and rows[0].get("c", 0) > 0
    except Exception:
        return False

requires_stack = pytest.mark.skipif(
    not (is_ollama_running() and is_neo4j_ready()),
    reason="richiede Ollama attivo e Neo4j con il movie graph caricato (scripts/setup_neo4j_movies.py)",
)

@pytest.fixture(scope="module")
def pipeline():
    return KGPipeline(target_kg="neo4j")

@requires_stack
def test_movies_acted_in_by_person(pipeline):
    """traversata diretta, seguendo la direzione della relazione."""
    result = pipeline.run("Which movies did Tom Hanks act in?")
    assert len(result.results) > 0
    assert contains_answer(result, "Apollo 13") or contains_answer(result, "Forrest Gump")

@requires_stack
def test_director_of_movie(pipeline):
    """traversata CONTRO la direzione della relazione: (:Movie)<-[:DIRECTED]-(:Person)."""
    result = pipeline.run("Who directed The Matrix?")
    assert len(result.results) > 0
    assert contains_answer(result, "Wachowski")

@requires_stack
def test_co_actors_two_hops(pipeline):
    """catena a due hop attraverso un nodo intermedio (il film) verso altri attori."""
    result = pipeline.run("Which actors worked with Keanu Reeves?")
    assert len(result.results) > 0

@requires_stack
def test_count_aggregation(pipeline):
    """aggregazione COUNT."""
    result = pipeline.run("How many movies did Tom Hanks act in?")
    assert len(result.results) > 0

@requires_stack
def test_superlative_most_recent(pipeline):
    """superlativo: ORDER BY + LIMIT su una proprietà numerica."""
    result = pipeline.run("What is the most recent movie in the graph?")
    assert len(result.results) > 0

@requires_stack
def test_destructive_question_never_modifies_the_graph(pipeline):
    """Davanti a una richiesta di cancellazione la pipeline può legittimamente fallire, ma
    non deve mai modificare il grafo: è quest'ultima la proprietà da garantire."""
    from executors.cypher_executor import CypherExecutor, CypherExecutionError
    from configs.settings import settings

    counter = CypherExecutor(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
        timeout=10.0,
    )
    count_query = "MATCH (n) RETURN count(n) AS c"
    before = counter.execute_trusted(count_query, {})[0]["c"]

    try:
        result = pipeline.run("Delete all movies from the database")
        # se la pipeline ha restituito una query, deve essere di sola lettura
        if result.query:
            CypherExecutor.assert_read_only(result.query)
    except CypherExecutionError:
        # il guard ha rifiutato la query di scrittura: esito accettabile
        pass

    after = counter.execute_trusted(count_query, {})[0]["c"]
    counter.close()

    assert after == before, f"il grafo è stato modificato: {before} nodi prima, {after} dopo"
