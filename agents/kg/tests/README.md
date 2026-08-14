# Suite di test dell'agente kg

260 test, divisi in due famiglie con costi molto diversi:
- i test di unità, che verificano la logica deterministica senza interpellare il modello;
- i test end-to-end, che eseguono la pipeline completa contro un knowledge graph reale e quindi dipendono da Ollama e dalla rete.

I test che richiedono un servizio non raggiungibile vengono saltati.

## Composizione di ciascuna directory

| directory | test | dipendenze | cosa verifica |
|---|---:|---|---|
| `api/` | 4 | ollama (1 test) | contratto degli endpoint fastapi |
| `cache/` | 17 | nessuna | cache semantica: soglia di similarità, invalidazione, isolamento fra domande |
| `configs/` | 2 | nessuna | coerenza delle impostazioni e presenza dei prompt |
| `correctors/` | 3 | ollama | riscrittura di una query fallita a partire dal messaggio d'errore |
| `executors/` | 42 | endpoint sparql | esecuzione, timeout e classificazione degli errori (distinguere un guasto transitorio da una query sbagliata) |
| `linkers/` | 22 | ollama | ordinamento dei candidati e disambiguazione delle menzioni |
| `pruners/` | 4 | nessuna | formattazione dello schema neo4j letto per introspezione |
| `translators/` | 44 | ollama (8 test) | sanificazione della query generata: blocchi di codice, alias di aggregazione, `SERVICE` fuori dal `WHERE`, letterali di stringa da non toccare |
| `connectors/` | 29 | api pubbliche | ricerca entità, grounding dei risultati, comportamento quando il kg non risponde |
| `benchmarks/` | 23 | nessuna | la metrica di `benchmarks/evaluate_qald.py` su entrambi i knowledge graph: sono i numeri che finiscono nella tesi, e un difetto qui produce un punteggio plausibile invece di un errore |
| `wikidata/` | 34 | ollama + rete | pipeline end-to-end su Wikidata |
| `dbpedia/` | 17 | ollama + rete + indice dbpedia | pipeline end-to-end su DBpedia |
| `neo4j/` | 19 | ollama + istanza neo4j | pipeline end-to-end sul movie graph |

## Esecuzione

```bash
cd agents/kg
uv run pytest -q                       # tutto
uv run pytest -q tests/translators     # una directory sola
```

Per evitare i test più pesanti:

```bash
uv run pytest -q --ignore=tests/wikidata --ignore=tests/dbpedia --ignore=tests/neo4j
```
