# Valutazione e Benchmark dell'Agente Planner

Questo modulo ospita la suite di benchmarking automatizzata sviluppata per misurare rigorosamente le prestazioni dell'Agente Planner. Il sistema valuta l'efficienza logica, l'aderenza ai formati strutturati, la resilienza tramite cicli di auto-correzione e la qualità semantica dei piani generati attraverso diversi LLM, tra cui i provider locali e cloud (Ollama, Gemini, OpenRouter).

## Struttura della Directory

* **`run_benchmarks.py`**: Orchestratore principale del benchmark logico e sintattico. Esegue i test in modo incrementale su un dataset predefinito e vari modelli, sollecitando l'agente e registrando le risposte, i crash e lo storico degli errori di validazione.
* **`run_semantic_eval.py`**: Pipeline di valutazione *LLM-as-a-judge* basata su un'architettura a cascata. Utilizza un modello giudice primario per il ragionamento qualitativo e un estrattore dedicato per il parsing rigoroso dell'output JSON.
* **`metrics/`**: Package Python per l'analisi dei risultati. È suddiviso in moduli a responsabilità singola (aggregazione, analitica, formattazione) che operano in memoria senza side-effects per calcolare le metriche finali, producendo report strutturati in JSON e Markdown.
* **`data/`**: Directory dedicata alla persistenza degli artefatti e ai report:
  * `benchmark_dataset.json`: Il *golden dataset* strutturato per intenti, domini (study, travel, routine, unknown), difficoltà e target specifici (es. time_math, impossible_schedule).
  * `benchmark_results.json` e `semantic_eval_results.json`: File di stato incrementali che consentono di riprendere le esecuzioni interrotte ignorando i test già elaborati.
  * `benchmark_report.md` e `benchmark_report.json`: L'output finale contenente la valutazione globale e i breakdown dettagliati per modello.
  * `benchmark_report_old.md`: Contiene la versione precedente del report con soli 10 casi di esecuzione, conservato per permettere il confronto con la versione aggiornata e documentare l'evoluzione delle prestazioni.

## Analisi dei Risultati e Insights

L'espansione del dataset di test da 10 a 30 casi per i modelli più promettenti ha introdotto vincoli rigorosi, tra cui complessi calcoli temporali (`time_math`) e agende irrealizzabili (`impossible_schedule`). Questo stress test ha messo in luce dinamiche architetturali fondamentali:

* **Stabilità dei Provider Cloud**: I modelli commerciali, come `gemini-3.6-flash` e `gemini-3.5-flash-lite`, hanno dimostrato una notevole capacità di generalizzazione. Passando da 10 a 30 test, hanno mantenuto un tasso di successo del 100%, registrando un impatto minimo sulla qualità semantica complessiva (da 5.00 a 4.80 per la versione 3.6).
* **Impatto della Scala e Parametri (Scaling Laws)**: Analizzando il comportamento della batteria completa di modelli, emerge una chiara correlazione tra la stazza del modello (numero di parametri) e la capacità di orchestrare formattazione rigida e logica:
  * **Heavyweights (Massive Open-Weights)**: Modelli con un numero colossale di parametri, come `nemotron-3-ultra-550b-a55b`, dimostrano prestazioni quasi paragonabili ai modelli commerciali top di gamma. Con un tasso di successo del 92% e una semantica eccellente (4.65), confermano che la potenza bruta aiuta enormemente a gestire vincoli multipli senza degradare il formato.
  * **Mid-Weights (10B - 30B)**: Modelli come `gpt-oss-20b` offrono un solido compromesso (successo dell'87.5% e score semantico a 4.51), dimostrando una buona comprensione delle istruzioni e stabilità strutturale, pur con risorse infrastrutturali accessibili.
  * **Small-Weights (3B - 8B) e Difficoltà Strutturali**: Questa è la fascia più problematica e turbolenta. Modelli come `qwen3:4b` e `phi4-mini` palesano evidenti limiti di *instruction following* strutturale e logico. `qwen3:4b` presenta un tasso *zero-shot* estremamente basso (37.5%) richiedendo costanti correzioni, mentre `phi4-mini` collassa quasi completamente durante i tentativi di recupero (tasso di fallimento della correzione del 100%). Per questi modelli, il carico cognitivo di dover rispettare uno schema JSON complesso e, simultaneamente, elaborare calcoli aritmetici è eccessivo.
* **Cedimenti nelle Architetture Locali di Fascia Media**: Il modello `llama3.2`, che sui test iniziali (10 casi) rappresentava il compromesso ideale, ha subito un forte ridimensionamento affrontando richieste più complesse. Il suo tasso di successo è sceso all'80% e il punteggio semantico è crollato a 3.56. In particolar modo, la percentuale di test che ha richiesto l'intervento del validatore è salita al 32%.
* **Problemi Sistemici e Resilienza**: L'aumento della complessità ha fatto emergere un tasso di crash globale del 3.48% (assente nei test base). Questa statistica è trainata dai cedimenti di `laguna-s-2.1` (con un crash rate del 23.33% sui casi aggiuntivi, imputabile unicamente a fallimenti delle chiamate all'API del provider e non a problemi di ragionamento del modello) e dai timeout di esecuzione che hanno afflitto `llama3.2` sotto carico.
* **Evoluzione dei Colli di Bottiglia Logici**: Mentre sui 10 test base l'errore di validazione preponderante era la sovrapposizione degli orari (`sovrapposizione_orari`, 99 occorrenze), nei test espansi l'errore critico è divenuto il calcolo errato delle durate (`duration_minutes_non_valido`, 122 occorrenze). Questo evidenzia una specifica debolezza generalizzata nel ragionamento aritmetico, portando il tasso di fallimento globale dei cicli di autocorrezione dal 20% al 30.95%.
* **Il Paradosso dei Modelli Ultra-Leggeri**: Architetture estremamente compatte come `qwen3:1.7b` riescono a bypassare i problemi strutturali superando i test semplici in modalità infallibile (*zero-shot* al 100%). Tuttavia, raggiungono questo risultato producendo output estremamente schematici, rigidi e qualitativamente insoddisfacenti (score semantico fermo a 3.17), eludendo la reale difficoltà del task.

## Flusso di Lavoro (Workflow)

Per eseguire l'intera pipeline di valutazione, il flusso prevede tre passaggi sequenziali:

1. **Esecuzione dei Benchmark Logici**
   Avvia la generazione dei piani e verifica la validazione JSON strutturale contro il dataset.
   ```bash
   python run_benchmarks.py
   ```

2. **Valutazione Semantica (LLM-as-a-Judge)**
   Analizza i risultati validi per valutare qualitativamente la fattibilità e la pertinenza dei piani generati.
   ```bash
   python run_semantic_eval.py
   ```

3. **Generazione del Report**
   Elabora i risultati grezzi e calcola le metriche statistiche globali, generando la documentazione di sintesi e di dettaglio (in `data/benchmark_report.md`).
   ```bash
   python -m metrics
   ```
