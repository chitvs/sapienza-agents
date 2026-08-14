# Laboratorio di Ingegneria Informatica

## Architettura del sistema

```text
sapienza-agents/
├── shared/                         # moduli python condivisi
├── ui/                             # interfaccia web comune agli agenti
├── orchestrator/                   # orchestratore centrale langgraph
└── agents/
    ├── kg/                         # agente knowledge graph
    ├── planner/                    # agente planner
    └── multiapi/                   # agente multiapi
```

## Avvio da zero

### Ollama

Il sistema usa due modelli locali, da scaricare una volta sola:

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

Le dipendenze python dell'agente kg si installano una volta sola:

```bash
cd agents/kg
uv venv
uv pip install -r requirements.txt
```

il passaggio non è facoltativo: `uv venv` crea `agents/kg/.venv`, che tutti i comandi `uv run` successivi useranno da soli. senza, `uv run` esegue con l'ambiente che trova e i comandi qui sotto si fermano su `ModuleNotFoundError`.

gli indici ontologici di wikidata e dbpedia sono artefatti di build e vanno generati:

```bash
uv run python scripts/ingest_wikidata.py     # ~3300 proprietà, ~500 classi
uv run python scripts/ingest_dbpedia.py      # ~3000 proprietà, ~800 classi
```

poi si avvia neo4j e si carica il dataset del dominio cinema:

```bash
cd ../..
docker compose up -d neo4j
cd agents/kg
uv run python scripts/setup_neo4j_movies.py
```

il dataset è il movie graph ufficiale di neo4j. Resta nel volume `neo4j-data`, quindi non va ricaricato agli avvii successivi.

### Avvio

dalla root del repository:

```bash
docker compose up -d
```

avvia l'intera catena in ordine: neo4j, poi kg-agent, poi orchestratore, infine l'interfaccia.

il primo avvio è lento. il kg-agent precarica i modelli locali e al primo giro li scarica da huggingface: circa 2.7 gb, di cui 2 gb per il solo gliner, con le richieste non autenticate limitate in banda. finché non ha finito il servizio non risponde all'healthcheck e i servizi che dipendono da lui restano in attesa. per seguirlo:

```bash
docker compose logs -f kg-agent
```

quando compare `modelli pronti.` il sistema è utilizzabile. dagli avvii successivi i modelli sono nel volume `hf-cache` e il precaricamento richiede una ventina di secondi.

> [!NOTE]
> Per quanto riguarda i comandi `docker`, potrebbe essere necessario lanciarli con `sudo`, qualora l'utente non appartenga al gruppo docker.

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

| target_kg  | linguaggio | dati                                 | prerequisiti                         |
|------------|------------|--------------------------------------|--------------------------------------|
| `wikidata` | sparql     | endpoint pubblico query.wikidata.org | indice ontologico (vedi setup)       |
| `dbpedia`  | sparql     | endpoint pubblico dbpedia.org        | indice ontologico (vedi setup)       |
| `neo4j`    | cypher     | istanza locale, dominio cinema       | istanza avviata e dataset caricato   |

Wikidata e dbpedia hanno ontologie troppo grandi per stare in un prompt, quindi lo schema rilevante viene selezionato con una ricerca semantica su indice faiss. Lo schema di un grafo neo4j è invece piccolo e chiuso: viene letto per intero tramite introspezione, senza indici da costruire.

### Lingua

L'agente kg lavora in inglese. L'entity linking cerca le etichette inglesi dei knowledge graph e il retrieval dello schema usa `bge-small-en-v1.5`, che è monolingue: una domanda in un'altra lingua degrada il linking e il recupero delle proprietà prima ancora di arrivare alla traduzione in query.

La traduzione è quindi responsabilità dell'orchestratore, che normalizza la domanda in inglese prima di interpellare l'agente kg e riporta la risposta finale nella lingua in cui è stata posta. Gli altri agenti continuano a ricevere la domanda originale. Nell'interfaccia web questo vale per la modalità orchestratore; interrogando l'agente kg direttamente, la domanda va scritta in inglese.

### Struttura del codice

```text
agents/kg/
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── scripts/                        # costruzione indici faiss e caricamento dataset
├── benchmarks/                     # benchmark e esperimenti di ablazione
├── data/                           # indici faiss generati e report di valutazione
├── src/
│   ├── api/                        # endpoint fastapi
│   ├── cache/                      # cache semantica delle domande
│   ├── configs/                    # settings e prompt
│   ├── connectors/                 # accesso ai dati di ciascun kg
│   ├── correctors/                 # correzione delle query fallite
│   ├── executors/                  # esecuzione delle query
│   ├── linkers/                    # entity linking (gliner + llm)
│   ├── models/                     # accesso ai modelli locali e al client ollama
│   ├── providers/                  # factory dei componenti per kg
│   ├── pruners/                    # selezione dello schema da passare all'llm
│   ├── translators/                # traduzione da linguaggio naturale a query
│   ├── utils/                      # utilità di analisi testuale delle query
│   ├── pipeline.py                 # orchestratore della pipeline
│   └── main.py                     # entrypoint fastapi
└── tests/                          # pytest
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

Avvia il microservizio fastapi del kg agent:

```bash
cd agents/kg
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

in locale ollama può restare in ascolto sul solo `127.0.0.1`: il vincolo su `0.0.0.0` riguarda unicamente l'esecuzione in container.

interroga il microservizio:

```bash
curl -X POST "http://localhost:8000/query" \
    -H "Content-Type: application/json" \
    -d '{"question": "What is the birth date of Albert Einstein?"}'
```

per interrogare un knowledge graph diverso da wikidata:

```bash
curl -X POST "http://localhost:8000/query" \
    -H "Content-Type: application/json" \
    -d '{"question": "Who directed The Matrix?", "target_kg": "neo4j"}'
```

### Esecuzione tramite docker compose

Il container non ha accesso alla gpu, quindi installa la variante cpu-only di torch. gli indici faiss vengono montati come volume da `agents/kg/data`, che deve quindi essere già stato generato.

dopo una modifica al codice serve ricostruire l'immagine:

```bash
sudo docker compose build kg-agent && sudo docker compose up -d kg-agent
```

### Test

Per lanciare:

```bash
cd agents/kg
uv run pytest -q
```

Ulteriori dettagli [qui](agents/kg/tests/README.md).

### Benchmark

La valutazione dell'agente kg si fa su due benchmark pubblici della famiglia QALD, con la macro-F1 e le convenzioni del benchmark: [QALD-10](https://github.com/KGQA/QALD-10) per wikidata e lo split di test di [QALD-9-plus](https://github.com/KGQA/QALD_9_plus) per dbpedia.

```bash
cd agents/kg
uv run python benchmarks/evaluate_qald.py --sample 30 --gold executed
uv run python benchmarks/evaluate_qald.py --benchmark qald9plus --sample 30 --gold executed
```

accanto al benchmark vero e proprio, `benchmarks/ablations/` contiene gli esperimenti che giustificano le singole scelte di progetto: quale segnale usare nella disambiguazione delle entità, se la chiamata all'llm per il linking ripaghi il suo costo, se la rigenerazione di una query che non ha prodotto righe produca davvero una query diversa. Ulteriori dettagli [qui](agents/kg/benchmarks/README.md).
