# Laboratorio di Ingegneria Informatica

## Architettura del sistema

```text
sapienza-agents/
├── shared/                         # moduli python condivisi (ollama_client.py)
├── orchestrator/                   # orchestratore centrale langgraph (porta 8000)
└── agents/
    ├── kg/                         # agente knowledge graph (wikidata)
    ├── planner/                    # agente planner
    └── multiapi/                   # agente multiapi
```

---

## Agente kg

L'agente kg traduce domande in linguaggio naturale in query sparql eseguite direttamente su wikidata tramite llm zero-shot.

### struttura del codice

```text
agents/kg/
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── src/
│   ├── api/
│   ├── cache/
│   ├── configs/
│   ├── connectors/
│   ├── correctors/
│   ├── executors/
│   ├── linkers/
│   ├── pruners/
│   ├── translators/
│   ├── pipeline.py
│   └── main.py
└── tests/
```

### Configurazione vs code

per garantire la corretta risoluzione degli import di src e shared, crea il file .vscode/settings.json nella root del repository:

```json
{
    "python.analysis.extraPaths": [
        "./agents/kg/src",
        "./shared"
    ]
}
```

### Esecuzione in locale (senza docker)

assicurati che ollama sia attivo con il modello llama3.2:
```bash
ollama serve
```

avvia il microservizio fastapi del kg agent:
```bash
cd agents/kg
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

interroga il microservizio:
```bash
curl -X POST "http://localhost:8000/query" \
    -H "Content-Type: application/json" \
    -d '{"question": "Qual è la data di nascita di Albert Einstein?"}'
```

---

### Esecuzione tramite docker compose

dalla root del repository:

```bash
sudo docker compose up --build kg-agent
```

### Esecuzione della suite di test

```bash
cd agents/kg
uv run pytest -v
```
