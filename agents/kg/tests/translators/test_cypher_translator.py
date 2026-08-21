"""
Test della normalizzazione dell'output Cypher.
"""

import pytest
from translators.cypher_translator import CypherTranslator

def test_spurious_spaces_in_patterns_are_removed():
    query = "MATCH ( p:Person )-[:ACTED_IN]->( m:Movie ) RETURN m.title"
    assert CypherTranslator.sanitize(query) == "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m.title"

def test_the_trailing_semicolon_is_removed():
    assert CypherTranslator.sanitize("MATCH (n) RETURN n ;") == "MATCH (n) RETURN n"

@pytest.mark.parametrize(
    "query",
    [
        'MATCH (m:Movie) WHERE m.title = "Star Wars ( A New Hope )" RETURN m',
        "MATCH (m:Movie) WHERE m.title CONTAINS 'Episode IV ( 1977 )' RETURN m",
    ],
)
def test_string_literals_stay_untouched(query):
    assert CypherTranslator.sanitize(query) == query

def test_literals_stay_untouched_but_the_code_does_not():
    query = 'MATCH ( m:Movie {title: "Star Wars ( 1977 )"} ) RETURN m'
    expected = 'MATCH (m:Movie {title: "Star Wars ( 1977 )"}) RETURN m'
    assert CypherTranslator.sanitize(query) == expected

def test_the_feedback_prompt_names_the_relationships_used():
    translator = CypherTranslator.__new__(CypherTranslator)
    prompt = translator.generate_feedback_prompt(
        "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m", schema_context="schema"
    )
    assert "ACTED_IN" in prompt
    assert "DIRECTION" in prompt.upper()
