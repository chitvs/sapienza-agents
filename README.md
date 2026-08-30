# Laboratorio di Ingegneria Informatica

Sistema multi-agente che risponde a domande in linguaggio naturale interrogando knowledge graph, api pubbliche, e scomponendo le richieste di pianificazione in piani strutturati. Un progetto nato durante il corso di _Laboratorio di Ingegneria Informatica_ del prof. Roberto Navigli, all'Università degli Studi di Roma "La Sapienza".

## Indice

- [Architettura del sistema](#architettura-del-sistema)
- [Avvio da zero](#avvio-da-zero)
  - [Ollama](#ollama)
  - [Avvio](#avvio)
  - [Verifica](#verifica)
  - [Gestione dei container](#gestione-dei-container)
- [Agente kg](#agente-kg)
  - [Preparazione](#preparazione)
  - [Knowledge graph supportati](#knowledge-graph-supportati)
  - [Lingua](#lingua)
  - [Modelli](#modelli)
  - [Struttura del codice](#struttura-del-codice)
  - [Esecuzione in locale](#esecuzione-in-locale-senza-docker)
  - [Esecuzione tramite docker compose](#esecuzione-tramite-docker-compose)
  - [Test](#test)
  - [Benchmark](#benchmark)
- [Agente planner](#agente-planner)
- [Agente multiapi](#agente-multiapi)
  - [Intenti supportati](#intenti-supportati)
  - [Configurazione](#configurazione)
  - [Cache](#cache)
  - [Struttura del codice](#struttura-del-codice-1)
  - [Esecuzione in locale](#esecuzione-in-locale-senza-docker-1)
  - [Test](#test-1)
- [Autori](#autori)

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

L'agente kg richiede una preparazione una tantum necessaria prima del primo `docker compose up`: è descritta [qui](#preparazione).

> [!NOTE]
> Per quanto riguarda i comandi `docker`, potrebbe essere necessario lanciarli con `sudo`, qualora l'utente non appartenga al gruppo docker.

### Ollama

Il sistema usa tre modelli locali, da scaricare una volta sola:

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:7b-instruct
ollama pull llama3.2
```

ollama va avviato in ascolto su tutte le interfacce, non solo su localhost:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

> [!WARNING]
> è un passaggio obbligatorio se si usa docker, e va rifatto a ogni riavvio della macchina. I container raggiungono l'host attraverso il gateway della rete docker, mentre ollama di default ascolta solo su `127.0.0.1` e rifiuta quelle connessioni. Il sintomo è `connection refused` verso `host.docker.internal` a ogni domanda.

### Avvio

(se non attivo) avviare docker con:

```bash
systemctl start docker
```

Dalla root del repository:

```bash
docker compose up -d
```

avvia l'intera catena in ordine: neo4j, poi i tre agenti (kg, planner, multiapi), poi l'orchestratore, infine l'interfaccia.

> [!NOTE]
> il primo avvio è lento. L'avanzamento si può seguire con `docker compose logs -f`, o `docker compose logs -f <servizio>` per uno solo.

### Verifica

Verificare la salute dei servizi con i seguenti comandi:

```bash
curl -s -o /dev/null -w "kg-agent %{http_code}\n"       localhost:8000/health
curl -s -o /dev/null -w "planner-agent %{http_code}\n"  localhost:8001/health
curl -s -o /dev/null -w "multiapi-agent %{http_code}\n" localhost:8002/health
curl -s -o /dev/null -w "orchestrator %{http_code}\n"   localhost:8080/health
curl -s -o /dev/null -w "ui %{http_code}\n"             localhost:3000/
```

Lanciare una domanda vera lungo tutta la catena, dall'interfaccia fino all'agente che la gestisce:

```bash
curl -X POST localhost:3000/api/orchestrator/query \
    -H "Content-Type: application/json" \
    -d '{"question": "Che tempo fa a Roma?"}'
```

Visualizzare la web ui: http://localhost:3000.

### Gestione dei container

I container si possono gestire con i seguenti comandi:

| comando | effetto |
|---|---|
| `docker compose restart` | riavvia i processi, ignora le modifiche a `docker-compose.yml` |
| `docker compose up -d` | ricrea solo i servizi la cui immagine o configurazione è cambiata |
| `docker compose up -d --force-recreate` | ricrea tutti i container, anche quelli invariati |
| `docker compose up -d --build --force-recreate` | come sopra, ricostruendo anche le immagini |
| `docker compose down && docker compose up -d` | rimuove container e rete, poi li ricrea da zero |

dopo una modifica al codice serve `--build`. Per intervenire su un solo servizio conviene aggiungere `--no-deps`, altrimenti compose tira su anche le dipendenze e si ripaga a ogni giro il precaricamento dei modelli, ad esempio:

```bash
docker compose up -d --build --no-deps orchestrator
```

> [!WARNING]
> `docker compose down -v` cancella anche i volumi: `neo4j-data`, con il dataset cinema da ricaricare via `scripts/setup_neo4j_movies.py`, e `hf-cache`, con i 2.2 gb di modelli da riscaricare.

## Agente kg

L'agente kg traduce domande in linguaggio naturale in query eseguite su un knowledge graph, tramite llm zero-shot. Supporta tre knowledge graph, selezionabili per richiesta con il campo `target_kg`.

### Preparazione

Installare le dipendeze python:

```bash
cd agents/kg
uv venv
uv pip install -r requirements.txt
```

generare gli indici ontologici di wikidata e dbpedia:

```bash
uv run python scripts/ingest_wikidata.py     # ~3300 proprietà, ~500 classi
uv run python scripts/ingest_dbpedia.py      # ~3000 proprietà, ~800 classi
```

avviare neo4j e caricare il dataset del dominio cinema:

```bash
cd ../..
docker compose up -d neo4j
cd agents/kg
uv run python scripts/setup_neo4j_movies.py
```

il dataset è il movie graph ufficiale di neo4j. Resta nel volume `neo4j-data`, quindi non va ricaricato agli avvii successivi.

### Knowledge graph supportati

| target_kg  | linguaggio | dati                                 | prerequisiti                         |
|------------|------------|--------------------------------------|--------------------------------------|
| `wikidata` | sparql     | endpoint pubblico query.wikidata.org | indice ontologico (vedi setup)       |
| `dbpedia`  | sparql     | endpoint pubblico dbpedia.org        | indice ontologico (vedi setup)       |
| `neo4j`    | cypher     | istanza locale, dominio cinema       | istanza avviata e dataset caricato   |

Wikidata e dbpedia hanno ontologie troppo grandi per stare in un prompt, quindi lo schema rilevante viene selezionato con una ricerca semantica su indice faiss. Lo schema di un grafo neo4j è invece piccolo e chiuso e quindi viene letto per intero tramite introspezione, senza indici da costruire.

### Lingua

L'agente kg lavora in inglese. L'entity linking cerca le etichette inglesi dei knowledge graph e il retrieval dello schema usa `bge-small-en-v1.5`, che è monolingue: una domanda in un'altra lingua degrada il linking e il recupero delle proprietà prima ancora di arrivare alla traduzione in query.

La traduzione è quindi responsabilità dell'orchestratore, che normalizza la domanda in inglese prima di interpellare l'agente kg e riporta la risposta finale nella lingua in cui è stata posta. Gli altri agenti continuano a ricevere la domanda originale. Nell'interfaccia web questo vale per la modalità orchestratore; interrogando l'agente kg direttamente, la domanda va scritta in inglese.

### Modelli

L'agente usa due modelli ollama con ruoli distinti:

- `qwen2.5-coder:7b` per la generazione delle query, che è un compito di scrittura di codice
- `qwen2.5:7b-instruct` per l'entity linking, dove il modello generico disambigua meglio di quello specializzato in codice

Entrambi sono configurabili da `.env` (vedi `.env.example`).

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

### Esecuzione in locale (senza docker)

Avviare il microservizio fastapi del kg agent:

```bash
cd agents/kg
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

in locale ollama può restare in ascolto sul solo `127.0.0.1`: il vincolo su `0.0.0.0` riguarda unicamente l'esecuzione in container.

interrogare il microservizio:

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

Il container non ha accesso alla gpu, quindi installa la variante cpu-only di torch. Gli indici faiss vengono montati come volume da `agents/kg/data`, che deve quindi essere già stato generato.

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

accanto al benchmark vero e proprio, `benchmarks/ablations/` contiene gli esperimenti che giustificano le singole scelte di progetto: quale segnale usare nella disambiguazione delle entità, se la chiamata all'llm per il linking ripaghi il suo costo, se la rigenerazione di una query che non ha prodotto righe produca davvero una query diversa. `benchmarks/baselines/` pone invece le stesse domande al modello senza knowledge graph, per distinguere quanto del punteggio venga dal grafo e quanto dalla conoscenza già nei pesi. Ulteriori dettagli, e i risultati delle due run complete, [qui](agents/kg/benchmarks/README.md).

## Agente planner

L'agente planner è un microservizio specializzato nello scomporre richieste in linguaggio naturale in piani temporali strutturati (formato JSON). Quando l'orchestratore rileva un intento di pianificazione, delega l'intera esecuzione a questo agente. Il planner dispone di un proprio modulo di context gathering che decide se e come interrogare `kg_agent` e `multiapi_agent` per arricchire il piano con dati reali (es. meteo, entità) prima di procedere alla generazione, attraverso una modalità ReAct, deterministica oppure disabilitata.

### Domini supportati

L'agente classifica internamente le richieste in uno dei seguenti domini:

| dominio | scopo | esempi |
|---|---|---|
| `study` | Preparazione esami, piani di studio, obiettivi didattici. | "Devo preparare Reti in 3 settimane" |
| `travel` | Itinerari di viaggio, vacanze, visite strutturate. | "Organizzami un weekend a Firenze" |
| `routine` | Abitudini giornaliere/settimanali e ritmi lavorativi. | "Struttura le mie giornate lavorative" |

Il dominio `unknown` viene usato per isolare e respingere le richieste fuori scope (es. "Che tempo fa domani?"). Oltre a generare piani da zero, il sistema supporta l'intento di *replanning*, elaborando aggiornamenti mirati su un piano già esistente.

### Context gathering

Prima di generare il piano, il planner decide se e come recuperare dati reali da `kg_agent` e `multiapi_agent` (es. meteo, entità) tramite tre modalità, selezionabili con `context_gathering_mode`:

- **`react`** (default): il modello decide autonomamente, passo per passo, quali tool chiamare, fino a un massimo di `max_react_steps` iterazioni.

- **`deterministic`**: i tool da interrogare sono determinati esplicitamente dalla richiesta tramite `allowed_tools`; il modello viene utilizzato solo per formulare le sotto-domande necessarie, non per decidere quali tool chiamare.

- **`none`**: nessun context gathering, il piano viene generato solo dalla richiesta dell'utente.

Il default globale è `react` con `max_react_steps=3`.
La modalità può essere modificata globalmente tramite `settings.py`
oppure sovrascritta per singola richiesta tramite `context_mode`.

### Resilienza

Il planner è progettato per non fallire mai in modo silenzioso quando il context gathering esterno va storto (kg-agent o multiapi-agent non raggiungibili, timeout, tool inesistente, ecc.): ogni fallimento viene registrato esplicitamente in `contingency_notes` invece di essere ignorato, e la `confidence` del piano ha un floor configurabile (`confidence_floor`, default `0.5`, anch'esso solo in `settings.py`) così un problema esterno non la fa mai scendere a zero.


### Configurazione

L'agente planner supporta l'esecuzione tramite modelli locali (Ollama) o provider cloud (Gemini, OpenRouter). 

Copiare `.env.example` in `.env` per configurare l'ambiente.

L'engine attivo viene stabilito dalla variabile `LLM_PROVIDER` (valori ammessi: `ollama`, `gemini`, `openrouter` o un ID specifico). A seconda della scelta, valorizzare le relative chiavi nel file `.env`:

- **Ollama**: Non richiede chiavi API, ma il servizio deve essere raggiungibile all'indirizzo configurato in `OLLAMA_HOST`.
- **Gemini**: Richiede una `GEMINI_API_KEY` valida. Ottenibile gratuitamente su [Google AI Studio](https://aistudio.google.com/app/apikey).
- **OpenRouter**: Richiede una `OPENROUTER_API_KEY` valida. Creabile su [OpenRouter](https://openrouter.ai/keys).

> **Attenzione:** Nell'impostare la lista dei modelli per `OPENROUTER_MODELS`, i valori devono essere separati da virgole, senza spazi intermedi e rigorosamente su una singola riga (es. `"openai/gpt-oss-20b:free,nvidia/nemotron-3.5-lightning:free"`).

Se il provider selezionato è Gemini o OpenRouter e la relativa chiave manca (o la chiamata fallisce), il client ripiega automaticamente su Ollama, loggando solo un warning — comportamento regolato da `ENABLE_LOCAL_FALLBACK` (default `true`). Con `ENABLE_LOCAL_FALLBACK=false` la richiesta fallisce invece di ripiegare silenziosamente.

#### Auto-discovery dei modelli

Il microservizio espone un endpoint di *discovery* non bloccante (`/models`) progettato per fornire alla UI un elenco dinamico dei modelli pronti all'uso:
- Contatta il demone **Ollama** per elencare i modelli attualmente scaricati sulla macchina.
- Interroga le API di **Google** per elencare i modelli Gemini attivi, escludendo automaticamente le varianti sperimentali, audio o vision (non adatte alla generazione JSON).
- Aggiunge la lista statica di modelli configurata per **OpenRouter** nel file `.env`. Non è stato scelto appositamente di aggiungere la discovery automatica dei modelli anche per OpenRouter data la mole di modelli disponibili che avrebbe appesantito la chiamata.

Per verificare i modelli rilevati:

```bash
curl -s localhost:8001/models
```

### Struttura del codice 

```text
agents/planner/
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── .env.example
├── benchmarks/                     # suite di valutazione (dataset, metriche, report)
│   ├── data/                       # golden dataset e risultati dei test (json/md)
│   └── metrics/                    # moduli di analisi, calcolo metriche e rendering report
├── src/
│   ├── api/                        # endpoint fastapi, schemi pydantic e server-sent events
│   ├── clients/                    # client http condiviso e wrapper llm
│   ├── configs/                    # settings e prompt testuali (drafting, replan, react)
│   ├── core/                       # logica: pipeline, context gathering, tools, validatori
│   ├── utils/                      # utilità di logging ed eventi
│   └── main.py                     # entrypoint fastapi
└── tests/                          # test unitari e di integrazione (pytest)
    ├── api/                        # test sugli endpoint http
    ├── integration/                # test di flusso end-to-end della pipeline
    ├── pipeline/                   # test sui singoli step (classificazione, contesto, finalizzazione)
    ├── tools/                      # test di resilienza e mocking dei tool esterni
    └── validators/                 # test sul validatore logico e strutturale dei piani
```    

### Esecuzione in locale (senza docker)

```bash
cd agents/planner/src
python main.py
```

```bash
curl -X POST localhost:8001/query -H "Content-Type: application/json" -d '{"question": "Devo preparare l'\''esame di Reti in 3 settimane, studio 2 ore al giorno nei feriali"}'
```

### Test

```bash
cd agents/planner
python -m pytest -q
```

La maggior parte dei test (`tests/pipeline`, `tests/tools`, `tests/validators`, `tests/configs`) mocka pipeline e client llm e gira offline in frazioni di secondo. I test su `tests/api` e `tests/integration` invocano invece la pipeline reale end-to-end: richiedono un provider llm raggiungibile (Ollama in ascolto, oppure `GEMINI_API_KEY` valorizzata) e vengono **saltati** altrimenti tramite il marker `@pytest.mark.requires_llm`. Ulteriori dettagli [agents/planner/tests/README.md](agents/planner/tests/README.md).

### Benchmark

Il planner ha una suite di benchmark separata dai test: dataset golden multi-dominio, valutazione su più provider/modelli e report di affidabilità e struttura in markdown. Metodologia, dataset e risultati completi in [agents/planner/benchmarks/README.md](agents/planner/benchmarks/README.md).

## Agente multiapi

L'agente multiapi risponde a domande in linguaggio naturale interrogando api pubbliche. Un llm classifica l'intento della domanda, un secondo prompt ne estrae i parametri, e il provider corrispondente chiama l'api. A differenza dell'agente kg lavora direttamente in italiano: non ha bisogno della traduzione dell'orchestratore.

### Intenti supportati

| intent | api | api key | esempi |
|---|---|---|---|
| `weather` | [Open-Meteo](https://open-meteo.com) | no | "Che tempo fa a Roma?", "Pioverà domani a Milano?" |
| `exchange_rate` | [Frankfurter](https://frankfurter.dev) | no | "Quanto sono 100 dollari in euro?", "Quanto valeva il cambio dollaro euro il 14 Aprile 2026?" |
| `country_info` | [countries.dev](https://countries.dev) | no | "Quanti abitanti ha il Giappone?" |
| `time_info` | world-time-api3 su RapidAPI | **sì** | "Che ore sono a Tokyo?" |

Il meteo distingue le condizioni correnti dalle previsioni: `days_ahead` viene estratto dalla domanda (`null` = adesso, `0` = oggi, `1` = domani, fino a 6 giorni). Il cambio valuta converte un importo e accetta una data passata; nei giorni senza fixing usa l'ultimo disponibile e lo dichiara nel campo `requested_date`.

### Configurazione

Il solo provider che richiede una chiave è quello dell'ora locale. Copiare `.env.example` in `.env` e inserire la chiave RapidAPI **senza virgolette**: nella sintassi a lista di `docker-compose` le virgolette entrerebbero nel valore e RapidAPI risponderebbe `403`.

```bash
cd agents/multiapi
cp .env.example .env
```

In alternativa si può valorizzare `TIMEAPI_API_KEY` nel `.env` alla root, che `docker compose` carica da solo.

`/health` riporta lo stato di ciascun provider: senza chiave, `time_info` segnala `TIMEAPI_API_KEY mancante` mentre il servizio resta `ok`, perché gli altri tre continuano a funzionare.

```bash
curl -s localhost:8002/health
```

### Cache

Le risposte sono memorizzate con una scadenza per intento, proporzionata a quanto invecchia il dato: `time_info` non viene mai messo in cache (un orario riusato è per definizione sbagliato), il meteo dura 10 minuti, il cambio valuta un'ora, i dati di un paese un giorno. Il campo `cached` nella risposta dice se il risultato è stato riusato.

### Struttura del codice

```text
agents/multiapi/
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── .env.example
└── src/
    ├── api/                        # endpoint fastapi e schemi di richiesta/risposta
    ├── cache/                      # cache delle risposte con scadenza per intento
    ├── configs/                    # settings e prompt
    ├── correctors/                 # riprova quando il llm non produce json valido
    ├── providers/                  # un modulo per api esterna
    ├── pipeline.py                 # classificazione, estrazione, instradamento
    └── main.py                     # entrypoint fastapi
```

### Esecuzione in locale (senza docker)

```bash
cd agents/multiapi
uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8002
```

```bash
curl -X POST localhost:8002/query -H "Content-Type: application/json" -d '{"question": "Che tempo fa a Roma?"}'
```

### Test

```bash
cd agents/multiapi
python -m pytest -q
```

La suite si divide in due famiglie. I test di unità (`test_*_offline.py`, `test_robustezza_llm.py`) usano risposte finte e girano in frazioni di secondo senza rete. I test di integrazione interrogano le api vere e Ollama, e vengono **saltati** quando il servizio non è raggiungibile o la chiave non è configurata: le sonde stanno in `tests/conftest.py`. Questo evita sia i fallimenti offline sia il consumo della quota gratuita di RapidAPI a ogni esecuzione.

## Autori

Sviluppato da Alessandro Chitarrini, Matteo Crugliano e Davide Gaglione.
