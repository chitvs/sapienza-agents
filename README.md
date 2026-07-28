# Laboratorio di Ingegneria Informatica

## Agenti supportati

### Interrogazione knowledge graphs (chitvs)

Nella cartella `agents/kg` è presente l'implementazione del microservizio di interrogazione di knowledge graphs.

Struttura del codice:

```text
agents/kg/
├── pytest.ini              # configurazione di pytest per il discovery dei moduli
├── requirements.txt        # dipendenze
├── src/
│   ├── connectors/         # estrazione dati dai grafi
│   │   ├── base.py
│   │   └── wikimedia.py
│   └── translators/        # Text2kglanguage
│       └── base.py
│       └── sparql.py       # Text2SPARQL
└── tests/                  # test di integrazione
    └── test_wikimedia.py
```

Per evitare warning relativi agli import, su vscode creare una cartella chiamata `.vscode` nella root e creare un file `settings.json` con dentro:

```json
{
    "python.analysis.extraPaths": [
        "./agents/kg/src"
    ]
}
```

#### Connectors

Interagiscono che le API dei knowledge graph e hanno due compiti principali:

- `search_entity`: text -> lista di entità con quel nome.
- `get_entity`: entità -> dati di quell'entità.

#### Linkers

Si occupano del processo chiamato entity linking. Utilizzano la seguente funzione:

- `link`: associa le entità al testo (utilizzando le funzioni grezze dei connettori).

#### Translators

Convertono il linguaggio naturale in una query per un knowledge graph tramite:

- `translate`: text -> query kg

#### Testing

Nella cartella `tests` sono presenti alcuni test da effettuare con pytest.
Per runnare:

Entrare nella cartella corretta e creare/attivare il virtual environment:

```bash
cd ~/sapienza-agents/agents/kg
uv venv
source .venv/bin/activate
```

Installare le dipendenze:

```bash
uv pip install -r requirements.txt
```

Ora è il momento di lanciare i test (`-v` sta per 'verbose'):

##### Tutti i test

```bash
uv run pytest -v
```

##### Test del connector wikimedia

```bash
uv run pytest tests/test_wikimedia.py -v
```
