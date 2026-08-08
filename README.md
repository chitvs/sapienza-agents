# Laboratorio di Ingegneria Informatica

## Architettura del sistema

```text
sapienza-agents/
├── shared/                         # moduli python condivisi (ollama_client.py)
├── ui/                             # interfaccia web comune agli agenti (porta 3000)
├── orchestrator/                   # orchestratore centrale langgraph (porta 8080)
└── agents/
    ├── kg/                         # agente knowledge graph (wikidata, dbpedia, neo4j)
    ├── planner/                    # agente planner
    └── multiapi/                   # agente multiapi
```

## Avvio da zero

### Ollama

il sistema usa due modelli locali, da scaricare una volta sola:

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:7b-instruct
```

ollama va avviato in ascolto su tutte le interfacce, non solo su localhost:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

è un passaggio obbligatorio se si usa docker, e va rifatto a ogni riavvio della macchina. i container raggiungono l'host attraverso il gateway della rete docker, mentre ollama di default ascolta solo su `127.0.0.1` e rifiuta quelle connessioni. il sintomo è `connection refused` verso `host.docker.internal` a ogni domanda.

### Preparazione

gli indici ontologici di wikidata e dbpedia sono artefatti di build e vanno generati:

```bash
cd agents/kg
uv run python scripts/ingest_wikidata.py     # ~3300 proprietà, ~500 classi
uv run python scripts/ingest_dbpedia.py      # ~3000 proprietà, ~800 classi
```

poi si avvia neo4j e si carica il dataset del dominio cinema:

```bash
cd ../..
sudo docker compose up -d neo4j
cd agents/kg
uv run python scripts/setup_neo4j_movies.py
```

il dataset è il movie graph ufficiale di neo4j. Resta nel volume `neo4j-data`, quindi non va ricaricato agli avvii successivi.

### Avvio

dalla root del repository:

```bash
sudo docker compose up -d ui
```

avvia l'intera catena in ordine: neo4j, poi kg-agent, poi orchestratore, infine l'interfaccia.

il primo avvio è lento. il kg-agent precarica i modelli locali e al primo giro li scarica da huggingface: circa 2.7 gb, di cui 2 gb per il solo gliner, con le richieste non autenticate limitate in banda. finché non ha finito il servizio non risponde all'healthcheck e i servizi che dipendono da lui restano in attesa. per seguirlo:

```bash
sudo docker compose logs -f kg-agent
```

quando compare `modelli pronti.` il sistema è utilizzabile. dagli avvii successivi i modelli sono nel volume `hf-cache` e il precaricamento richiede una ventina di secondi.

### Verifica

salute dei servizi:

```bash
curl -s -o /dev/null -w "kg-agent %{http_code}\n"     localhost:8000/health
curl -s -o /dev/null -w "orchestrator %{http_code}\n" localhost:8080/health
curl -s -o /dev/null -w "ui %{http_code}\n"           localhost:3000/
```

una domanda vera lungo tutta la catena, dall'interfaccia fino al grafo:

```bash
curl -X POST localhost:3000/api/kg/query \
    -H "Content-Type: application/json" \
    -d '{"question": "Who directed The Matrix?", "target_kg": "neo4j"}'
```

poi apri http://localhost:3000.

## Agente kg

L'agente kg traduce domande in linguaggio naturale in query eseguite su un knowledge graph, tramite llm zero-shot. Supporta tre knowledge graph, selezionabili per richiesta con il campo `target_kg`.

### Knowledge graph supportati

| target_kg  | linguaggio | dati                                | prerequisiti                         |
|------------|------------|-------------------------------------|--------------------------------------|
| `wikidata` | sparql     | endpoint pubblico query.wikidata.org | indice ontologico (vedi setup)       |
| `dbpedia`  | sparql     | endpoint pubblico dbpedia.org        | indice ontologico (vedi setup)       |
| `neo4j`    | cypher     | istanza locale, dominio cinema       | istanza avviata e dataset caricato   |

Wikidata e dbpedia hanno ontologie troppo grandi per stare in un prompt, quindi lo schema rilevante viene selezionato con una ricerca semantica su indice faiss. Lo schema di un grafo neo4j è invece piccolo e chiuso: viene letto per intero tramite introspezione, senza indici da costruire.

### Struttura del codice

```text
agents/kg/
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── scripts/                        # costruzione indici e caricamento dataset
├── data/                           # indici faiss generati
├── src/
│   ├── api/                        # endpoint fastapi
│   ├── cache/                      # cache semantica delle domande
│   ├── configs/                    # settings e prompt
│   ├── connectors/                 # accesso ai dati di ciascun kg
│   ├── correctors/                 # correzione delle query fallite
│   ├── executors/                  # esecuzione delle query
│   ├── linkers/                    # entity linking (gliner + llm)
│   ├── providers/                  # factory dei componenti per kg
│   ├── pruners/                    # selezione dello schema da passare all'llm
│   ├── translators/                # traduzione da linguaggio naturale a query
│   ├── pipeline.py
│   └── main.py
└── tests/
```

Ogni knowledge graph è un provider che compone i propri connector, translator, executor, pruner e corrector.

### Modelli

L'agente usa due modelli ollama con ruoli distinti:

- `qwen2.5-coder:7b` per la generazione delle query, che è un compito di scrittura di codice
- `qwen2.5:7b-instruct` per l'entity linking, dove il modello generico disambigua meglio di quello specializzato in codice

Entrambi sono configurabili da `.env` (vedi `.env.example`).

### Configurazione VS Code

crea il file `.vscode/settings.json` nella root del repository:

```json
{
    "python.defaultInterpreterPath": "./agents/kg/.venv/bin/python",
    "python.analysis.extraPaths": [
        "./agents/kg/src",
        "./shared"
    ]
}
```

### Esecuzione in locale (senza docker)

avvia il microservizio fastapi del kg agent:

```bash
cd agents/kg
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

in locale ollama può restare in ascolto sul solo `127.0.0.1`: il vincolo su `0.0.0.0` riguarda unicamente l'esecuzione in container.

interroga il microservizio:

```bash
curl -X POST "http://localhost:8000/query" \
    -H "Content-Type: application/json" \
    -d '{"question": "Qual è la data di nascita di Albert Einstein?"}'
```

per interrogare un knowledge graph diverso da wikidata:

```bash
curl -X POST "http://localhost:8000/query" \
    -H "Content-Type: application/json" \
    -d '{"question": "Who directed The Matrix?", "target_kg": "neo4j"}'
```

### Esecuzione tramite docker compose

il container non ha accesso alla gpu, quindi installa la variante cpu-only di torch. gli indici faiss vengono montati come volume da `agents/kg/data`, che deve quindi essere già stato generato.

dopo una modifica al codice serve ricostruire l'immagine:

```bash
sudo docker compose build kg-agent && sudo docker compose up -d kg-agent
```

### Esecuzione della suite di test

```bash
cd agents/kg
uv run pytest -v
```

i test che richiedono ollama, neo4j o un endpoint pubblico vengono saltati se il servizio non è raggiungibile, invece di fallire. la suite completa richiede molto tempo, quasi del tutto speso nei test di integrazione su wikidata: per un giro veloce si può escludere quella directory.

```bash
uv run pytest -q --ignore=tests/integration
```
