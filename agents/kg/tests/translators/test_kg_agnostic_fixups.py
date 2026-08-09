"""
Test delle euristiche strutturali di riparazione delle query SPARQL.

Le euristiche ragionano sul grafo della query (quali variabili sono legate, quali sono
solo hop intermedi, quali filtri di tipo sono ridondanti) e sono quindi condivise fra
tutti i KG SPARQL: qui si verifica che producano lo stesso risultato su Wikidata e su
DBpedia, che hanno sintassi completamente diverse.
"""
import pytest
from translators.sparql_translator import (
    DBpediaSPARQLTranslator,
    WikidataSPARQLTranslator,
)

def test_unbound_select_label_is_redirected_wikidata():
    query = """SELECT ?cityLabel WHERE {
      wd:Q937 wdt:P26 ?spouse.
      ?spouse wdt:P19 ?birthPlace.
    }"""
    fixed = WikidataSPARQLTranslator._fix_unbound_select_label(query)
    assert "?cityLabel" not in fixed
    assert "?birthPlaceLabel" in fixed

def test_unbound_select_label_is_redirected_dbpedia():
    """
    Stessa euristica, sintassi dbpedia: la variabile va proiettata nuda. Il suffisso Label
    è magia di SERVICE wikibase:label, che dbpedia non ha: lì ?xLabel non sarebbe legata da
    nulla e Virtuoso proietterebbe righe senza valore invece di segnalare un errore.
    """
    query = """SELECT ?cityLabel WHERE {
      dbr:Albert_Einstein dbo:spouse ?spouse.
      ?spouse dbo:birthPlace ?birthPlace.
    }"""
    fixed = DBpediaSPARQLTranslator._fix_unbound_select_label(query)
    assert "?cityLabel" not in fixed
    assert "?birthPlaceLabel" not in fixed
    assert "?birthPlace" in fixed

def test_intermediate_hop_is_redirected_to_leaf_wikidata():
    query = """SELECT ?capitalLabel WHERE {
      wd:Q17 wdt:P36 ?capital.
      ?capital wdt:P1082 ?population.
    }"""
    fixed = WikidataSPARQLTranslator._fix_intermediate_hop_label(query)
    assert "?populationLabel" in fixed

def test_intermediate_hop_is_redirected_to_leaf_dbpedia():
    query = """SELECT ?capitalLabel WHERE {
      dbr:Japan dbo:capital ?capital.
      ?capital dbo:populationTotal ?population.
    }"""
    fixed = DBpediaSPARQLTranslator._fix_intermediate_hop_label(query)
    assert "?populationLabel" not in fixed
    assert "?population" in fixed

@pytest.mark.parametrize(
    "translator, query",
    [
        (
            WikidataSPARQLTranslator,
            "SELECT ?countryLabel WHERE { ?country wdt:P31 wd:Q6256. ?country wdt:P2046 ?area. }"
            " ORDER BY DESC(?area) LIMIT 1",
        ),
        (
            DBpediaSPARQLTranslator,
            "SELECT ?mountain WHERE { ?mountain a dbo:Mountain . ?mountain dbo:elevation ?elevation . }"
            " ORDER BY DESC(?elevation) LIMIT 1",
        ),
        (
            WikidataSPARQLTranslator,
            "SELECT ?cityLabel WHERE { ?city wdt:P31 wd:Q515. ?city wdt:P1082 ?pop. FILTER(?pop > 250000) }",
        ),
    ],
)
def test_ordering_and_filter_variables_are_never_projected(translator, query):
    """
    In un superlativo o in un filtro la foglia è il criterio di selezione, non la risposta.
    Proiettarla farebbe rispondere con la superficie invece che con il nome del paese, e
    siccome le righe non sarebbero vuote nessun retry se ne accorgerebbe.
    """
    assert translator.__new__(translator).postprocess(query, "x") == query

def test_bound_label_variable_is_left_alone():
    """
    Se ?xLabel è già legata nel WHERE la query è corretta: riscriverla produrrebbe una
    tripla che confronta una risorsa con la propria etichetta, cioè zero righe.
    """
    query = "SELECT ?nameLabel WHERE { dbr:The_Matrix dbo:director ?director . ?director rdfs:label ?nameLabel . }"
    assert DBpediaSPARQLTranslator._fix_unbound_select_label(query) == query

def test_where_body_is_never_rewritten():
    """Le riparazioni riguardano la proiezione: toccare il WHERE cambierebbe il grafo interrogato."""
    query = "SELECT ?capitalLabel WHERE { wd:Q17 wdt:P36 ?capital. ?capital wdt:P1082 ?population. }"
    fixed = WikidataSPARQLTranslator._fix_intermediate_hop_label(query)
    assert "WHERE { wd:Q17 wdt:P36 ?capital. ?capital wdt:P1082 ?population. }" in fixed

@pytest.mark.parametrize(
    "translator, query",
    [
        (
            WikidataSPARQLTranslator,
            "SELECT ?x WHERE { wd:Q937 wdt:P19 ?p. ?p wdt:P31 wd:Q3257686. }",
        ),
        (
            DBpediaSPARQLTranslator,
            "SELECT ?x WHERE { dbr:Albert_Einstein dbo:birthPlace ?p. ?p a dbo:City. }",
        ),
    ],
)
def test_redundant_class_filter_on_reached_variable_is_removed(translator, query):
    """
    La variabile è già raggiunta da una proprietà specifica: il filtro di tipo è
    ridondante e può essere rimosso quando la query non restituisce righe.
    """
    relaxed = translator.relax_class_filters(query)
    assert relaxed is not None
    assert "P31" not in relaxed and " a dbo:City" not in relaxed

@pytest.mark.parametrize(
    "translator, query",
    [
        (
            WikidataSPARQLTranslator,
            "SELECT ?l WHERE { ?c wdt:P31 wd:Q6256. ?c wdt:P37 ?l. ?c wdt:P2046 ?a. } ORDER BY DESC(?a) LIMIT 1",
        ),
        (
            DBpediaSPARQLTranslator,
            "SELECT ?l WHERE { ?c a dbo:Country. ?c dbo:language ?l. ?c dbo:areaTotal ?a. } ORDER BY DESC(?a) LIMIT 1",
        ),
    ],
)
def test_class_filter_on_free_variable_is_never_removed(translator, query):
    """
    In un superlativo la variabile iterata non ha archi entranti: il filtro di tipo è
    l'unico vincolo che la definisce. Rimuoverlo darebbe una risposta sbagliata al posto
    di nessuna risposta, che è un esito peggiore.
    """
    assert translator.relax_class_filters(query) is None

def test_duplicate_select_variables_are_removed():
    """
    Virtuoso rifiuta una variabile proiettata due volte ("column specified multiple
    times"). Capita quando il modello riusa lo stesso nome per due ruoli diversi.
    """
    query = (
        "SELECT ?elevation ?elevation WHERE { ?elevation a dbo:Mountain . "
        "?elevation dbo:elevation ?elevation . } ORDER BY DESC(?elevation) LIMIT 1"
    )
    fixed = DBpediaSPARQLTranslator.sanitize_sparql(query)
    assert fixed.count("?elevation ?elevation") == 0
    assert "SELECT ?elevation WHERE" in fixed

def test_distinct_is_preserved_when_deduplicating():
    fixed = WikidataSPARQLTranslator.sanitize_sparql("SELECT DISTINCT ?x ?x WHERE { ?x wdt:P31 wd:Q5. }")
    assert "SELECT DISTINCT ?x WHERE" in fixed

def test_distinct_variables_are_left_alone():
    query = "SELECT ?mountain ?elevation WHERE { ?mountain dbo:elevation ?elevation. }"
    assert "?mountain ?elevation" in DBpediaSPARQLTranslator.sanitize_sparql(query)

def test_aggregation_alias_is_not_touched():
    """Le espressioni con alias non vanno riscritte: non sono un elenco di variabili."""
    query = "SELECT (COUNT(?film) AS ?count) WHERE { ?film dbo:director dbr:X. }"
    assert "(COUNT(?film) AS ?count)" in DBpediaSPARQLTranslator.sanitize_sparql(query)
