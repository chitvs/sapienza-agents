"""
Test della normalizzazione dell'output Cypher.

Il traduttore Cypher non aveva alcuna prova offline, a differenza dei due SPARQL: le sue
riparazioni sono sintattiche e testabili senza Neo4j né LLM.
"""
import pytest

from translators.cypher_translator import CypherTranslator

def test_gli_spazi_spuri_nei_pattern_vengono_tolti():
    query = "MATCH ( p:Person )-[:ACTED_IN]->( m:Movie ) RETURN m.title"
    assert CypherTranslator.sanitize(query) == "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m.title"

def test_il_punto_e_virgola_finale_viene_rimosso():
    """Dentro una transazione esplicita il punto e virgola finale è rifiutato."""
    assert CypherTranslator.sanitize("MATCH (n) RETURN n ;") == "MATCH (n) RETURN n"

@pytest.mark.parametrize(
    "query",
    [
        'MATCH (m:Movie) WHERE m.title = "Star Wars ( A New Hope )" RETURN m',
        "MATCH (m:Movie) WHERE m.title CONTAINS 'Episode IV ( 1977 )' RETURN m",
    ],
)
def test_i_letterali_di_stringa_restano_intatti(query):
    """Normalizzare dentro un titolo cambia il film cercato: la query resta valida e
    restituisce zero righe, così il ciclo ReAct riparte su una causa inesistente."""
    assert CypherTranslator.sanitize(query) == query

def test_i_letterali_restano_intatti_ma_il_codice_no():
    """Le due cose devono convivere nella stessa query."""
    query = 'MATCH ( m:Movie {title: "Star Wars ( 1977 )"} ) RETURN m'
    atteso = 'MATCH (m:Movie {title: "Star Wars ( 1977 )"}) RETURN m'
    assert CypherTranslator.sanitize(query) == atteso

def test_il_prompt_di_feedback_cita_le_relazioni_usate():
    """Il feedback deve dire quali relazioni non hanno funzionato, o il modello le ripete."""
    translator = CypherTranslator.__new__(CypherTranslator)
    prompt = translator.generate_feedback_prompt(
        "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) RETURN m", schema_context="schema"
    )
    assert "ACTED_IN" in prompt
    assert "DIRECTION" in prompt.upper()
