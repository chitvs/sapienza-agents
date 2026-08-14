# Suite di test dell'agente kg

275 test, divisi in due famiglie con costi molto diversi:
- i test di unità, che verificano la logica deterministica senza interpellare il modello;
- i test end-to-end, che eseguono la pipeline completa contro un knowledge graph reale e quindi dipendono da Ollama e dalla rete.

I test che richiedono un servizio non raggiungibile vengono saltati. Le sonde dei servizi stanno tutte in `conftest.py` e sono memorizzate: definirle nei singoli file costava una chiamata di rete alla raccolta, pagata anche da chi lanciava una directory che quel servizio non lo tocca. Per la stessa ragione le tre directory end-to-end sono le uniche a interrogare la rete: tutto ciò che sta altrove gira offline.

## Composizione di ciascuna directory

| directory | test | dipendenze | cosa verifica |
|---|---:|---|---|
| `api/` | 5 | ollama (1 test) | contratto degli endpoint fastapi e rilascio delle connessioni allo spegnimento |
| `cache/` | 17 | modello di embedding in cache locale | cache semantica: soglia di similarità, invalidazione, isolamento fra domande |
| `configs/` | 2 | nessuna | coerenza delle impostazioni e presenza dei prompt |
| `correctors/` | 3 | ollama (1 test) | riscrittura di una query fallita a partire dal messaggio d'errore |
| `executors/` | 42 | nessuna | guardia di sola lettura, timeout e classificazione degli errori (distinguere un guasto transitorio da una query sbagliata) |
| `linkers/` | 22 | ollama (2 test) | ordinamento dei candidati e disambiguazione delle menzioni |
| `pipeline/` | 4 | nessuna | percorso a zero righe: distinguere un grafo che non ha il dato da un endpoint irraggiungibile |
| `pruners/` | 7 | nessuna | formattazione dello schema neo4j e prefissi con cui le classi vengono citate all'llm |
| `translators/` | 43 | ollama (4 test) | sanificazione della query generata: blocchi di codice, alias di aggregazione, `SERVICE` fuori dal `WHERE`, letterali di stringa da non toccare |
| `connectors/` | 22 | nessuna | escaping degli identificatori, grounding dei risultati e comportamento quando il kg non risponde (simulato) |
| `benchmarks/` | 30 | nessuna | la metrica di `benchmarks/evaluate_qald.py` su entrambi i knowledge graph: sono i numeri che finiscono nella tesi, e un difetto qui produce un punteggio plausibile invece di un errore |
| `wikidata/` | 39 | ollama + rete | pipeline end-to-end su Wikidata, più le api e l'endpoint sparql interrogati davvero |
| `dbpedia/` | 20 | ollama + rete + indice dbpedia | pipeline end-to-end su DBpedia, più la lookup api interrogata davvero |
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
