"""Registro dei knowledge graph supportati."""

from providers.base_provider import BaseProvider

def build_provider(target_kg: str) -> BaseProvider:
    """Istanzia il provider del KG richiesto."""
    kg = (target_kg or "").strip().lower()

    if kg in ("", "wikidata"):
        from providers.wikidata_provider import WikidataProvider
        return WikidataProvider()
    if kg == "neo4j":
        from providers.neo4j_provider import Neo4jProvider
        return Neo4jProvider()
    if kg == "dbpedia":
        from providers.dbpedia_provider import DBpediaProvider
        return DBpediaProvider()

    raise ValueError(
        f"knowledge graph non supportato: '{target_kg}'. "
        f"valori ammessi: 'wikidata', 'dbpedia', 'neo4j'."
    )
