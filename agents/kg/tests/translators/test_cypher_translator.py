"""
Test della normalizzazione dell'output Cypher.

Il traduttore Cypher non aveva alcuna prova offline, a differenza dei due SPARQL: le sue
riparazioni sono sintattiche e testabili senza Neo4j né LLM.
"""
import pytest

from translators.cypher_translator import CypherTranslator

def test_spurious_spaces_in_patterns_are_removed():
    query = "MATCH ( p:Person )-[:ACTED_IN]->( m:Movie ) RETURN m.title"
    assert CypherTranslator.sanitize(query) == "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m.title"

def test_the_trailing_semicolon_is_removed():
    """Dentro una transazione esplicita il punto e virgola finale è rifiutato."""
    assert CypherTranslator.sanitize("MATCH (n) RETURN n ;") == "MATCH (n) RETURN n"

@pytest.mark.parametrize(
    "query",
    [
        'MATCH (m:Movie) WHERE m.title = "Star Wars ( A New Hope )" RETURN m',
        "MATCH (m:Movie) WHERE m.title CONTAINS 'Episode IV ( 1977 )' RETURN m",
    ],
)
def test_string_literals_stay_untouched(query):
    """Normalizzare dentro un titolo cambia il film cercato: la query resta valida e
    restituisce zero righe, così il ciclo ReAct riparte su una causa inesistente."""
    assert CypherTranslator.sanitize(query) == query

def test_literals_stay_untouched_but_the_code_does_not():
    """Le due cose devono convivere nella stessa query."""
    query = 'MATCH ( m:Movie {title: "Star Wars ( 1977 )"} ) RETURN m'
    expected = 'MATCH (m:Movie {title: "Star Wars ( 1977 )"}) RETURN m'
    assert CypherTranslator.sanitize(query) == expected

def test_the_feedback_prompt_names_the_relationships_used():
    """Il feedback deve dire quali relazioni non hanno funzionato, o il modello le ripete."""
    translator = CypherTranslator.__new__(CypherTranslator)
    prompt = translator.generate_feedback_prompt(
        "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m", schema_context="schema"
    )
    assert "ACTED_IN" in prompt
    assert "DIRECTION" in prompt.upper()
