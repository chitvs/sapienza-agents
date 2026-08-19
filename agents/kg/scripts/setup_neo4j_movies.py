"""
Carica il movie graph ufficiale di Neo4j nell'istanza configurata.

Uso:
    python scripts/setup_neo4j_movies.py            # carica il dataset
    python scripts/setup_neo4j_movies.py --reset    # svuota il grafo e ricarica
    python scripts/setup_neo4j_movies.py --check    # ispeziona il grafo

Attenzione: --reset esegue DETACH DELETE su tutti i nodi.
"""

import argparse
import sys
from pathlib import Path
from typing import Any
import requests
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from configs.settings import settings

# sorgente ufficiale del dataset
MOVIES_CYPHER_URL = "https://raw.githubusercontent.com/neo4j-graph-examples/movies/main/scripts/movies.cypher"

def get_driver() -> Any:
    """Apre il driver verso l'istanza configurata in .env."""
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

def session_kwargs() -> dict[str, str]:
    """Seleziona il database solo se configurato, altrimenti si usa quello di default."""
    return {"database": settings.neo4j_database} if settings.neo4j_database else {}

def check(driver: Any) -> None:
    """Stampa un riepilogo del contenuto del grafo."""
    with driver.session(**session_kwargs()) as session:
        labels = [r["label"] for r in session.run("CALL db.labels() YIELD label RETURN label")]
        rel_types = [
            r["relationshipType"]
            for r in session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        ]
        total = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]

        print(f"nodi totali: {total}")
        print(f"label: {labels or '(nessuna)'}")
        print(f"tipi di relazione: {rel_types or '(nessuno)'}")

        for label in labels:
            count = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS c").single()["c"]
            print(f"  (:{label}) -> {count} nodi")

def reset(driver: Any) -> None:
    """Svuota completamente il grafo."""
    with driver.session(**session_kwargs()) as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("grafo svuotato.")

def split_statements(script: str) -> list[str]:
    """Divide lo script Cypher nei singoli statement separati da ';'."""
    statements: list[str] = []
    current: list[str] = []
    quote_char: str | None = None
    escaped = False

    for char in script:
        if quote_char:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = None
            continue

        if char in ("'", '"'):
            quote_char = char
            current.append(char)
        elif char == ";":
            statements.append("".join(current))
            current = []
        else:
            current.append(char)

    statements.append("".join(current))
    return [s.strip() for s in statements if s.strip()]

def load(driver: Any) -> None:
    """Scarica ed esegue lo script Cypher ufficiale del movie graph."""
    print(f"scarico il dataset da {MOVIES_CYPHER_URL} ...")
    response = requests.get(MOVIES_CYPHER_URL, timeout=60)
    response.raise_for_status()

    statements = split_statements(response.text)
    print(f"lo script contiene {len(statements)} statement.")

    with driver.session(**session_kwargs()) as session:
        existing = session.run("MATCH (n) WHERE n:Movie RETURN count(n) AS c").single()["c"]
        if existing:
            print(
                f"il grafo contiene già {existing} nodi :Movie — nessuna modifica. "
                f"usa --reset per ricaricarlo da zero."
            )
            return

        print("carico il dataset ...")
        for i, statement in enumerate(statements, start=1):
            try:
                session.run(statement)
            except Exception as err:
                print(f"  statement {i}/{len(statements)} fallito: {err}")
                print(f"  query: {statement[:200]}")
                raise

    print(f"dataset caricato ({len(statements)} statement eseguiti).")

def main() -> None:
    parser = argparse.ArgumentParser(description="carica il movie graph ufficiale di Neo4j")
    parser.add_argument("--reset", action="store_true", help="svuota il grafo prima di caricare")
    parser.add_argument("--check", action="store_true", help="mostra soltanto il contenuto del grafo")
    args = parser.parse_args()

    print(f"istanza neo4j: {settings.neo4j_uri} (database: {settings.neo4j_database or 'default'})")
    driver = get_driver()

    try:
        driver.verify_connectivity()
    except Exception as err:
        sys.exit(
            f"impossibile connettersi a {settings.neo4j_uri}: {err}\n"
            f"verifica che l'istanza sia avviata e che NEO4J_USER/NEO4J_PASSWORD in .env siano corretti."
        )

    try:
        if args.check:
            check(driver)
            return

        if args.reset:
            confirm = input("questo cancellerà tutti i nodi del database. scrivi 'si' per continuare: ")
            if confirm.strip().lower() not in ("si", "sì", "yes", "y"):
                sys.exit("annullato.")
            reset(driver)

        load(driver)
        print()
        check(driver)
    finally:
        driver.close()

if __name__ == "__main__":
    main()
