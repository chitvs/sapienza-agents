"""
Test dell'estrazione della query dal blocco markdown prodotto dal modello.

Non serve un LLM: si verifica il parsing dell'output grezzo, che è il punto in cui un tag
di linguaggio inatteso finiva in testa alla query e la faceva rifiutare dall'endpoint.
"""
import pytest

from shared.ollama_client import OllamaClient

@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        ("```sparql\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        # il tag può essere qualunque: elencarne solo alcuni lasciava "text" nella query
        ("```text\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        ('```javascript\n{"selected_id": "Q1"}\n```', '{"selected_id": "Q1"}'),
        ("```\nSELECT ?x WHERE {}\n```", "SELECT ?x WHERE {}"),
        # blocco tutto su una riga: la prima parola è contenuto, non un tag
        ("```SELECT ?x WHERE {}```", "SELECT ?x WHERE {}"),
        ("```sparql SELECT ?x WHERE {}```", "SELECT ?x WHERE {}"),
        # blocco non chiuso, tipico quando il modello viene troncato
        ('```json\n{"a": 1}', '{"a": 1}'),
        ("SELECT ?x WHERE {}", "SELECT ?x WHERE {}"),
        ("Sure! ```cypher\nMATCH (n) RETURN n\n``` spero sia utile", "MATCH (n) RETURN n"),
    ],
)
def test_code_block_is_stripped(grezzo, atteso):
    assert OllamaClient.clean_code_block(grezzo) == atteso
