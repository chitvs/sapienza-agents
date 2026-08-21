# Valutazione dell'agente kg

La cartella contiene tre cose diverse, che conviene non confondere:

- due benchmark pubblici, entrambi eseguiti da `evaluate_qald.py`;
- tre esperimenti interni in `ablations/`, divisi su cinque script, che non misurano la qualità del sistema ma giustificano singole scelte di progetto;
- una baseline in `baselines/`, che risponde alle stesse domande senza knowledge graph e dà un termine di paragone al punteggio della pipeline.

Tutti gli script si lanciano dalla directory `agents/kg` e scrivono i risultati in `data/evaluations/`.

## I benchmark: QALD-10 e QALD-9-plus

`evaluate_qald.py` valuta la pipeline su due dataset della famiglia QALD, che condividono lo stesso formato e la stessa metrica ma insistono su knowledge graph diversi. Il knowledge graph non si sceglie: è una proprietà del dataset, e l'opzione `--benchmark` seleziona entrambi insieme.

| benchmark | dataset | kg | domande |
|---|---|---|---:|
| `qald10` (default) | [QALD-10](https://github.com/KGQA/QALD-10) | wikidata | 394 |
| `qald9plus` | [QALD-9-plus](https://github.com/KGQA/QALD_9_plus), split di test | dbpedia | 150 |

```bash
uv run python benchmarks/evaluate_qald.py --gold executed                       # qald-10, tutte
uv run python benchmarks/evaluate_qald.py --benchmark qald9plus --gold executed # qald-9-plus, tutte
uv run python benchmarks/evaluate_qald.py --sample 30                           # campione stratificato
uv run python benchmarks/evaluate_qald.py --dry-run                             # solo la composizione
```

Di QALD-9-plus si valuta lo split di test; il train non servirebbe, dato che la pipeline è zero-shot. Il dataset è multilingue, ma qui si usa la sola formulazione inglese, perché l'agente kg lavora in inglese e la traduzione è responsabilità dell'orchestratore.

La metrica è la macro-F1 con le convenzioni QALD, riportata anche divisa per tipo di domanda: `ask`, `count`, `single` (un solo hop) e `multi`. Il tipo si deduce dalla query gold contando i predicati, e il conteggio è specifico del grafo: Wikidata cita le proprietà con `wdt:`/`p:`/`ps:`/`pq:`, mentre su DBpedia i predicati si riconoscono dalla convenzione dell'ontologia, che scrive in minuscolo le proprietà e in maiuscolo le classi. Il campione con `--sample` è stratificato, cioè mantiene le proporzioni fra i quattro tipi del dataset completo, e con lo stesso `--seed` restituisce sempre le stesse domande. Le proporzioni sono rispettate con il metodo dei resti massimi, quindi il campione ha esattamente la dimensione richiesta e una classe rara non viene sovrappesata; va però ricordato che il sottoinsieme dipende dalla classificazione, e che dopo una modifica a `question_kind` lo stesso seme non restituisce più le stesse domande.

L'opzione `--gold` sceglie le risposte di riferimento e cambia il significato del numero:

- `recorded` (default) usa le risposte registrate nel dataset, che risalgono alla sua costruzione;
- `executed` le rigenera eseguendo ora le query gold sull'endpoint. Le risposte rigenerate restano in cache accanto al dataset (`data/qald_10_executed.json`, `data/qald_9_plus_test_dbpedia_executed.json`), quindi il costo si paga una volta sola. Le query gold che falliscono non vengono messe in cache: un guasto transitorio dell'endpoint escluderebbe altrimenti quelle domande da ogni run futura, presentandosi come invecchiamento del dataset.

Su QALD-9-plus `--gold executed` non è un raffinamento ma una necessità: 35 delle 150 domande non hanno più alcuna risposta registrata, e su un gold vuoto la convenzione QALD «nessuna attesa, nessuna prodotta» assegnerebbe F1 = 1.0 anche a una pipeline che è esplosa. Le domande senza gold utilizzabile vengono quindi escluse, e il loro numero è stampato all'inizio della run. Su QALD-10 il problema è di natura diversa e più sottile: le risposte registrate ci sono quasi tutte, ma Wikidata nel frattempo è cambiata e sui conteggi il disallineamento è sistematico, così senza `--gold executed` si misura in parte l'età del dataset invece della qualità della nostra traduzione.

Il report completo, domanda per domanda con la query prodotta, finisce in `data/evaluations/<benchmark>_<timestamp>.json`.

Serve Ollama attivo e l'indice ontologico del grafo già costruito (`scripts/ingest_wikidata.py` o `scripts/ingest_dbpedia.py`).

## Risultati misurati

Le due run complete, eseguite con `--gold executed`.

| benchmark | kg | domande valutate | macro-F1 | ask | count | single | multi |
|---|---|---:|---:|---:|---:|---:|---:|
| QALD-10 | wikidata | 378 su 394 | **0.377** | 0.426 (61) | 0.218 (87) | 0.590 (125) | 0.225 (105) |
| QALD-9-plus (test) | dbpedia | 104 su 150 | **0.205** | 0.750 (4) | 0.250 (8) | 0.253 (41) | 0.117 (51) |

Fra parentesi il numero di domande di quel tipo. Le domande mancanti all'appello sono quelle escluse dal filtro sul gold utilizzabile descritto sopra: 16 su QALD-10, 46 su QALD-9-plus.

## Gli esperimenti in `ablations/`

Non producono un punteggio di sistema. Ognuno risponde a una domanda del tipo «questo componente serve davvero, e conviene tenerlo così com'è?». Sono tutti su Wikidata, perché usano i QID della query gold di QALD-10 come verità di riferimento.

### Disambiguazione delle entità: quale segnale usare

Quando l'LLM non sa scegliere fra i candidati di una menzione, la scelta ricade su un ranking basato su tre segnali: affinità della descrizione col contesto della domanda, notorietà dell'entità (numero di sitelink) e posizione restituita dalla ricerca. Questi due script misurano quale combinazione sbaglia meno.

```bash
uv run python benchmarks/ablations/disambiguation_collect.py 400   # raccolta, con rete
uv run python benchmarks/ablations/disambiguation_policies.py      # analisi, offline
```

Il primo estrae le menzioni con GLiNER, interroga Wikidata per i candidati e salva i tre segnali in `data/evaluations/disambiguation_signals.json`, usando come verità di riferimento i QID che compaiono nella query gold. Il secondo confronta sette politiche di combinazione su quel file, in un secondo e senza rete.

Il conteggio riguarda solo i casi in cui il QID corretto è fra i candidati, così misura l'ordinamento e non il richiamo della ricerca.

### Disambiguazione delle entità: l'LLM ripaga il suo costo?

```bash
uv run python benchmarks/ablations/disambiguation_llm.py
```

Riusa `disambiguation_signals.json` e confronta, sugli stessi casi, tre scelte: quella dell'LLM, quella del ranking senza LLM e quella banale del primo candidato.

### Rigenerazione ReAct: la seconda query è davvero diversa?

```bash
uv run python benchmarks/ablations/retry_collect.py --sample 40   # raccolta, con pipeline e llm
uv run python benchmarks/ablations/retry_analyze.py               # riepilogo, offline
```

Quando una query si esegue senza errori ma restituisce zero righe, la pipeline la rigenera passando al modello un prompt di feedback. L'esperimento arriva fino alla prima esecuzione e, sui casi a zero righe, rigenera a più configurazioni di campionamento (temperatura 0.0 e 1.0 con top-p 0.9) registrando quante volte l'output è identico all'originale e quante volte recupera righe. A temperatura bassa una rigenerazione identica costa una chiamata all'LLM per nulla, ed è il motivo per cui l'esperimento esiste.

## La baseline in `baselines/`

Il macro-F1 della pipeline, da solo, non dice se il knowledge graph stia aggiungendo accuratezza o soltanto verificabilità: `closed_book.py` pone le stesse domande allo stesso modello senza alcun accesso al grafo, e fornisce il termine di paragone.

```bash
uv run python benchmarks/baselines/closed_book.py --gold executed
uv run python benchmarks/baselines/closed_book.py --benchmark qald9plus --gold executed
```

Il `--gold` deve coincidere con quello usato per la pipeline, altrimenti i due numeri sono calcolati su riferimenti diversi e il confronto non significa nulla. Vengono scartate le stesse domande senza gold utilizzabile, così i due macro-F1 insistono sulla stessa popolazione. Il grafo interviene solo per costruire il riferimento e per risolvere le etichette in fase di punteggio: la baseline non lo interroga mai per rispondere. Al modello non viene detto che tipo di risposta ci si aspetta, perché dedurlo dalla domanda fa parte del compito esattamente come per la pipeline, che deve scegliere da sola fra `ASK`, `COUNT` e `SELECT`.

Si interroga `qwen2.5:7b-instruct` e non il modello di traduzione, che essendo specializzato sul codice sarebbe un avversario di comodo come baseline di conoscenza. Il riepilogo distingue le risposte che non rispettano il formato richiesto da quelle in cui il modello dichiara di non sapere, e il report finisce in `data/evaluations/closedbook_<benchmark>_<timestamp>.json`.
