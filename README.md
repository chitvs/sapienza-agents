# Laboratorio di Ingegneria Informatica

## Agenti supportati

### Interrogazione knowledge graphs (chitvs)

Nella cartella `agents/kg` è presente l'implementazione del microservizio di interrogazione di knowledge graphs.

Struttura del codice:

```text
agents/kg/
├── pytest.ini                  # configurazione di pytest per il discovery dei moduli
├── requirements.txt            # dipendenze
├── src/
│   ├── connectors/             # estrazione dati dai grafi
│   │   ├── base_connector.py
│   │   └── wikimedia_connector.py
│   ├── linkers/                # Entity Linking (testo -> QID)
│   │   ├── base_linker.py
│   │   └── lookup_linker.py
│   ├── translators/            # Text2kglanguage
│   │   ├── base_translator.py
│   │   └── sparql_translator.py
│   ├── executors/              # Esecuzione query su DB/Triplestore
│   │   ├── base_executor.py
│   │   └── sparql_executor.py
│   └── grounders/              # Symbol Grounding (QID -> Label umana)
│       ├── base_grounder.py
│       └── wikidata_grounder.py
└── tests/                      # test di integrazione
    ├── test_wikimedia_connector.py
    ├── test_lookup_linker.py
    ├── test_sparql_translator.py
    ├── test_sparql_executor.py
    └── test_wikidata_grounder.py

```

Per evitare warning relativi agli import, su VS Code creare una cartella chiamata `.vscode` nella root del progetto e creare un file `settings.json` con dentro:

```json
{
    "python.analysis.extraPaths": [
        "./agents/kg/src"
    ]
}
```

#### Connectors

Interagiscono con le API dei knowledge graph e hanno due compiti principali:

- `search_entity`: text -> lista di entità candidate con quel nome.
- `get_entity`: entity_id -> dati dettagliati di quell'entità.

#### Linkers

Si occupano del processo di entity linking:

- `link`: associa la menzione testuale al corrispondente ID univoco del grafo (es. "Einstein" -> Q937), appoggiandosi ai connettori.

#### Translators

Convertono il linguaggio naturale in una query formale per un knowledge graph tramite:

- `translate`: riceve la domanda dell'utente e il contesto sulle entità mappate (es. wd:Q937, wdt:P569), invoca LLM e restituisce la query.

#### Executors

Si occupano dell'esecuzione delle query generate sui database o triplestore target:

- `execute`: invia la query formattata all'endpoint di destinazione (es. Wikidata SPARQL endpoint) e restituisce i risultati grezzi.

#### Grounders

Si occupano del processo di symbol grounding e label resolution:

- `ground`: prende in input i dati grezzi restituiti dagli esecutori e risolve gli URI/QID nelle rispettive etichette leggibili in linguaggio naturale.

---

#### Testing

Nella cartella `tests` sono presenti i test di integrazione da effettuare con `pytest`.

Per eseguirli, entrare nella cartella corretta e attivare il virtual environment:

```bash
cd ~/sapienza-agents/agents/kg
uv venv
source .venv/bin/activate
```

Installare le dipendenze:

```bash
uv pip install -r requirements.txt
```

Eseguire i test (`-v` sta per 'verbose'):

##### Tutti i test

```bash
uv run pytest -v
```

##### Test dei singoli moduli

```bash
# Test connettori
uv run pytest tests/test_wikimedia_connector.py -v

# Test linker
uv run pytest tests/test_lookup_linker.py -v

# Test translator (richiede Ollama attivo)
uv run pytest tests/test_sparql_translator.py -v -s

# Test executor
uv run pytest tests/test_sparql_executor.py -v

# Test grounder
uv run pytest tests/test_wikidata_grounder.py -v
```
