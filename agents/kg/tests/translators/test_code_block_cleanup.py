"""
Test dell'estrazione della query dal blocco markdown.
"""

import pytest
from shared.ollama_client import OllamaClient

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("```sparql\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        ("```text\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        ('```javascript\n{"selected_id": "Q1"}\n```', '{"selected_id": "Q1"}'),
        ("```\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        ("```SELECT ?x WHERE {}```", "SELECT ?x WHERE {}"),
        ("```sparql SELECT ?x WHERE {}```", "SELECT ?x WHERE {}"),
        ('```json\n{"a": 1}', '{"a": 1}'),
        ("SELECT ?x WHERE {}", "SELECT ?x WHERE {}"),
        ("Sure! ```cypher\nMATCH (n) RETURN n\n``` hope it helps", "MATCH (n) RETURN n"),
    ],
)
def test_code_block_is_stripped(raw, expected):
    assert OllamaClient.clean_code_block(raw) == expected
