# Valutazione dell'agente Planner

> **Data Generazione:** `2026-08-29T15:34:17.098770+00:00`  
> **Test Totali:** `110`  
> **Modelli Valutati:** `11`

## Indice dei contenuti
- [1. Sintesi Esecutiva & Insights](#1-sintesi-esecutiva--insights)
- [2. Confronto tra modelli](#2-confronto-tra-modelli)
- [3. Valutazione semantica](#3-valutazione-semantica)
- [4. Breakdown per Dominio](#4-breakdown-per-dominio)
- [5. Breakdown per Difficoltà e Target](#5-breakdown-per-difficoltà-e-target)
- [6. Context Gathering](#6-context-gathering)
- [7. Errori di validazione e contesti esterni](#7-errori-di-validazione-e-contesti-esterni)
- [8. Dettaglio per test](#8-dettaglio-per-test)

---

## 1. Sintesi Esecutiva & Insights

> ### Sintesi dei risultati
> 
> - **Top Performer (Successo):** `qwen3:1.7b` con il **100.00%** di Supported Success.
> - **Miglior Qualità Semantica:** `gemini-3.6-flash` con uno score complessivo di **5.00 / 5**.
> - **Esecuzione più Fluida:** `qwen3:1.7b` (Zero-shot: 100.00%, Validation Rate: 0.00%).
> - **Collo di Bottiglia Principale:** L'errore di validazione più ricorrente è `sovrapposizione_orari` (99 occorrenze).
> - **Spreco Computazionale:** Il **20.00%** dei cicli di auto-correzione fallisce (Correction Failure Rate).

<details>
<summary><strong>Visualizza metriche globali (KPI e Diagnostica)</strong></summary>

### KPI Globali
- Supported Success Rate: `95.45%`
- Domain Accuracy: `96.36%`
- Semantic Overall Score: `4.39 / 5`
- System Crash Rate: `0.00%`

### Metriche Diagnostiche
- Zero-shot Rate: `77.27%`
- Recovery Rate: `80.00%`
- Correction Failure Rate: `20.00%`
- Validation Attempt Rate: `22.73%`
- Mean Validation Attempts (sui corretti): `1.45`
- Context Errors (media): `0.00`
- External Resilience: `0.00%`
- Non-empty Plan Rate: `95.45%`
- Unknown Domain Accuracy: `81.82%`
- Overconfidence Rate: `37.50%`

</details>

---

## 2. Confronto tra modelli

> **Spiegazione delle metriche (KPI):**
> - **Successo Supportato**: percentuale di test superati nei domini supportati (esclude i casi 'unknown' fuori scope).
> - **Accuratezza Dominio**: correttezza della classificazione del dominio (es. 'study' riconosciuto come 'study').
> - **Score Semantico**: valutazione qualitativa da LLM-as-a-judge, su una scala da 1 a 5 (più alto è meglio).
> - **Tasso Crash**: test terminati con eccezioni o errori di sistema.

### KPI Principali
| Modello | Test | Successo Supportato | Accuratezza Dominio | Score Semantico | Tasso Crash |
|:---|---:|---:|---:|---:|---:|
| `dots-3-note-preview` | 10 | 100.00% | 100.00% | 4.72 | 0.00% |
| `gemini-3.5-flash-lite` | 10 | 100.00% | 100.00% | 4.82 | 0.00% |
| `gemini-3.6-flash` | 10 | 100.00% | 100.00% | 5.00 | 0.00% |
| `gpt-oss-20b` | 10 | 87.50% | 100.00% | 4.51 | 0.00% |
| `laguna-s-2.1` | 10 | 100.00% | 90.00% | 4.51 | 0.00% |
| `llama3.2` | 10 | 100.00% | 100.00% | 4.07 | 0.00% |
| `ministral-3:3b` | 10 | 87.50% | 80.00% | 4.11 | 0.00% |
| `nemotron-3-ultra-550b-a55b` | 10 | 100.00% | 100.00% | 4.72 | 0.00% |
| `nemotron-3.5-lightning` | 10 | 100.00% | 90.00% | 4.66 | 0.00% |
| `qwen3:1.7b` | 10 | 100.00% | 100.00% | 3.17 | 0.00% |
| `qwen3:4b` | 10 | 75.00% | 100.00% | 3.88 | 0.00% |

> **Spiegazione delle metriche (Diagnostiche):**
> - **Zero-shot**: test superati al primo tentativo, senza bisogno di correzioni (massima efficienza).
> - **Recovery**: tra i test che hanno richiesto correzione, percentuale di quelli che sono infine riusciti.
> - **Fallimento Correzione**: percentuale di cicli di correzione che falliscono (spreco computazionale).
> - **Tasso Validazione**: test che hanno innescato almeno un errore di validazione strutturale.
> - **Media Validazioni**: numero medio di tentativi di correzione *solo sui test che hanno avuto errori*.
> - **Errori Contesto**: numero medio di fallimenti nelle chiamate a servizi esterni (API, KG, ecc.).
> - **Overconfidence**: percentuale di test falliti in cui l'agente aveva comunque una confidenza ≥ 0.8 (segnale di allucinazione).

### Metriche Diagnostiche
| Modello | Zero-shot | Recovery | Fallimento Correzione | Tasso Validazione | Media Validazioni | Errori Contesto | Overconfidence |
|:---|---:|---:|---:|---:|---:|---:|---:|
| `dots-3-note-preview` | 75.00% | 100.00% | 0.00% | 25.00% | 1.00 | 0.00 | 0.00% |
| `gemini-3.5-flash-lite` | 75.00% | 100.00% | 0.00% | 25.00% | 1.00 | 0.00 | 0.00% |
| `gemini-3.6-flash` | 87.50% | 100.00% | 0.00% | 12.50% | 1.00 | 0.00 | 0.00% |
| `gpt-oss-20b` | 75.00% | 50.00% | 50.00% | 25.00% | 2.00 | 0.00 | 0.00% |
| `laguna-s-2.1` | 75.00% | 100.00% | 0.00% | 25.00% | 1.00 | 0.00 | 100.00% |
| `llama3.2` | 75.00% | 100.00% | 0.00% | 25.00% | 1.00 | 0.00 | 0.00% |
| `ministral-3:3b` | 75.00% | 50.00% | 50.00% | 25.00% | 2.00 | 0.00 | 33.33% |
| `nemotron-3-ultra-550b-a55b` | 87.50% | 100.00% | 0.00% | 12.50% | 1.00 | 0.00 | 0.00% |
| `nemotron-3.5-lightning` | 87.50% | 100.00% | 0.00% | 12.50% | 1.00 | 0.00 | 100.00% |
| `qwen3:1.7b` | 100.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0.00 | 0.00% |
| `qwen3:4b` | 37.50% | 60.00% | 40.00% | 62.50% | 2.00 | 0.00 | 0.00% |

---

## 3. Valutazione semantica

> **Cosa misurano le dimensioni semantiche (1-5):**
> - **Groundedness**: il piano è ancorato al contesto fornito (orari, date, vincoli)?
> - **Aderenza**: risponde esattamente alla richiesta dell'utente?
> - **Fattibilità Umana**: è realistico e sostenibile per un essere umano?
> - **Granularità**: il livello di dettaglio è appropriato (né troppo vago, né troppo minuzioso)?
> - **Replanning**: nel caso di modifica di un piano esistente, mantiene coerenza con l'originale?
> - **Overall**: media aritmetica delle dimensioni valutate (solo se almeno 3 dimensioni sono disponibili).
> - **Copertura**: percentuale di test eleggibili che sono stati effettivamente valutati semanticamente.

| Modello | Groundedness | Aderenza | Fattibilità Umana | Granularità | Replanning | Overall | Copertura | Parziali | Non Validi |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `dots-3-note-preview` | 4.75 | 4.62 | 4.62 | 5.00 | 3.50 | **4.72** | 100.00% | 6 | 0 |
| `gemini-3.5-flash-lite` | 5.00 | 4.62 | 5.00 | 4.88 | 3.50 | **4.82** | 100.00% | 6 | 0 |
| `gemini-3.6-flash` | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 | **5.00** | 100.00% | 6 | 0 |
| `gpt-oss-20b` | 4.43 | 4.57 | 4.57 | 4.71 | 1.00 | **4.51** | 100.00% | 6 | 0 |
| `laguna-s-2.1` | 5.00 | 4.12 | 4.25 | 4.88 | 3.00 | **4.51** | 100.00% | 6 | 0 |
| `llama3.2` | 4.50 | 3.62 | 4.75 | 3.75 | 2.50 | **4.07** | 100.00% | 6 | 0 |
| `ministral-3:3b` | 3.86 | 4.43 | 3.86 | 4.71 | 3.00 | **4.11** | 100.00% | 5 | 0 |
| `nemotron-3-ultra-550b-a55b` | 4.75 | 4.25 | 5.00 | 5.00 | 3.50 | **4.72** | 100.00% | 6 | 0 |
| `nemotron-3.5-lightning` | 4.88 | 4.62 | 5.00 | 4.25 | 4.00 | **4.66** | 100.00% | 6 | 0 |
| `qwen3:1.7b` | 3.62 | 2.88 | 3.50 | 3.25 | 1.00 | **3.17** | 100.00% | 6 | 0 |
| `qwen3:4b` | 4.50 | 3.00 | 4.50 | 4.33 | 1.00 | **3.88** | 100.00% | 4 | 0 |

---

## 4. Breakdown per Dominio

> I dati sono aggregati per dominio atteso (`study`, `travel`, `routine`, `unknown`). 
> Questo permette di capire se l'agente performa meglio su alcune tipologie di richieste.

| Gruppo | Test | Successo Supportato | Accuratezza Dominio | Score Semantico | Tasso Crash |
|:---|---:|---:|---:|---:|---:|
| `routine` | 22 | 90.91% | 100.00% | 4.51 | 0.00% |
| `study` | 33 | 96.97% | 100.00% | 4.48 | 0.00% |
| `travel` | 33 | 96.97% | 100.00% | 4.24 | 0.00% |
| `unknown` | 22 | 0.00% | 81.82% | - | 0.00% |

---

## 5. Breakdown per Difficoltà e Target

> **Difficoltà:** `easy`, `medium`, `hard`. I target più complessi includono `time_math` (calcoli temporali), 
> `impossible_schedule` (richieste irrealizzabili) e `replan_deletion` (modifiche strutturali).
> Le celle mostrano: **Supported Success Rate** e, tra parentesi, il numero di test in quel gruppo.

### Supported Success Rate per Modello e Difficoltà

| Modello | easy | hard | medium |
|:---|---:|---:|---:|
| `dots-3-note-preview` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `gemini-3.5-flash-lite` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `gemini-3.6-flash` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `gpt-oss-20b` | 100.00% (6) | 100.00% (1) | 66.67% (3) |
| `laguna-s-2.1` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `llama3.2` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `ministral-3:3b` | 75.00% (6) | 100.00% (1) | 100.00% (3) |
| `nemotron-3-ultra-550b-a55b` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `nemotron-3.5-lightning` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `qwen3:1.7b` | 100.00% (6) | 100.00% (1) | 100.00% (3) |
| `qwen3:4b` | 50.00% (6) | 100.00% (1) | 100.00% (3) |

### Supported Success Rate per Modello e Test Target

| Modello | replan_deletion | replan_shift | standard_planning | vague_instructions |
|:---|---:|---:|---:|---:|
| `dots-3-note-preview` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `gemini-3.5-flash-lite` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `gemini-3.6-flash` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `gpt-oss-20b` | 100.00% (1) | 0.00% (1) | 100.00% (6) | 100.00% (2) |
| `laguna-s-2.1` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `llama3.2` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `ministral-3:3b` | 100.00% (1) | 100.00% (1) | 75.00% (6) | 100.00% (2) |
| `nemotron-3-ultra-550b-a55b` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `nemotron-3.5-lightning` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `qwen3:1.7b` | 100.00% (1) | 100.00% (1) | 100.00% (6) | 100.00% (2) |
| `qwen3:4b` | 100.00% (1) | 100.00% (1) | 50.00% (6) | 100.00% (2) |


---

## 6. Context gathering

> **Modalità testate:**
> - `deterministic`: usa una lista fissa di tool (es. kg_agent, multiapi_agent) definita a priori.
> - `react`: l'agente decide iterativamente quali tool chiamare in base al contesto.
> - `none`: nessun recupero di contesto esterno (solo ragionamento interno).
> La metrica *External Resilience* indica la percentuale di test che, nonostante errori nelle chiamate esterne, 
> sono comunque riusciti a produrre un piano valido.

### Modalità: `none`

- Test valutati: **110**
- Supported Success Rate: **95.45%**
- Domain Accuracy: **96.36%**
- Semantic score: **4.39 / 5**
- External resilience: **0.00%**
- Crash rate: **0.00%**

---

## 7. Errori di validazione e contesti esterni

<details>
<summary><strong>Dettaglio errori di validazione logica</strong></summary>

> **Cosa sono:** errori sollevati dal validatore strutturale quando il piano non rispetta lo schema JSON 
> o le regole logiche (es. orari sovrapposti, `duration_minutes` non numerico, giorno mancante).
> **Recuperati** = test che, dopo aver ricevuto questi errori, sono comunque riusciti a produrre un piano valido.

> **Legenda delle categorie di errore:**
> | Codice errore | Significato |
> |:---|:---|
> | `draft_vuoto_o_non_json` | Il piano restituito è vuoto o non è un JSON valido. |
> | `campo_title_mancante` | Manca il campo obbligatorio `title` del piano. |
> | `campo_summary_tipo_errato` | Il campo `summary` non è una stringa valida. |
> | `campo_contingency_notes_tipo_errato` | Il campo `contingency_notes` non è una lista di stringhe. |
> | `days_mancante_o_vuoto` | Il campo `days` (elenco dei giorni) è mancante o vuoto. |
> | `day_index_non_valido` | L'indice del giorno (`day_index`) non è un numero intero valido. |
> | `day_index_duplicato` | Due giorni consecutivi hanno lo stesso `day_index`. |
> | `campo_label_tipo_errato` | Il campo `label` (etichetta del giorno) non è una stringa. |
> | `formato_data_invalido` | Il campo `date` non rispetta il formato `YYYY-MM-DD`. |
> | `slots_mancanti_o_invalidi` | La lista `slots` è mancante, vuota o malformata. |
> | `campo_task_mancante` | Manca il campo obbligatorio `task` in uno slot. |
> | `campo_category_tipo_errato` | Il campo `category` non è tra quelli ammessi (`studio`, `visita`, `pasto`, ...). |
> | `campo_subtasks_tipo_errato` | Il campo `subtasks` non è una lista di stringhe. |
> | `campo_notes_tipo_errato` | Il campo `notes` non è una stringa valida. |
> | `duration_minutes_non_valido` | La durata (`duration_minutes`) non è un numero positivo. |
> | `formato_orario_invalido` | L'orario (`start_time`) non rispetta il formato `HH:MM`. |
> | `durata_totale_giornaliera_eccessiva` | La somma delle durate degli slot in un singolo giorno supera le 24 ore. |
> | `sovrapposizione_orari` | Due o più slot nello stesso giorno si sovrappongono temporalmente. |
> | `routine_giorni_incompleti` | Per il dominio `routine`, mancano alcuni giorni della settimana (devono esserci tutti, 1-7). |
> | `day_index_non_contiguo` | I `day_index` non formano una sequenza numerica contigua (es. 1, 2, 4). |
> | `replan_non_effettuato` | Nel caso di `replan`, il piano finale è identico a quello precedente. |
> | `altro` | Categoria di errore non riconosciuta dalle regex del validatore. |

- **Test con almeno un errore di validazione:** 9
- **Occorrenze complessive:** 225

| Categoria | Occorrenze | Test coinvolti | Recuperati |
|:---|---:|---:|---:|
| `sovrapposizione_orari` | 99 | 4 | 4 |
| `formato_orario_invalido` | 55 | 4 | 3 |
| `duration_minutes_non_valido` | 54 | 4 | 4 |
| `day_index_non_valido` | 5 | 4 | 2 |
| `draft_vuoto_o_non_json` | 2 | 2 | 1 |
| `slots_mancanti_o_invalidi` | 7 | 1 | 5 |
| `day_index_non_contiguo` | 1 | 1 | 1 |
| `routine_giorni_incompleti` | 1 | 1 | 0 |
| `days_mancante_o_vuoto` | 1 | 1 | 0 |

</details>

<details>
<summary><strong>Dettaglio fallimenti contesto esterno</strong></summary>

> **Cosa sono:** errori che si verificano durante la raccolta di informazioni da servizi esterni 
> (es. API meteo, orari di apertura, Knowledge Graph). Un test è *resiliente* se, nonostante questi errori, 
> riesce comunque a completare il piano senza crash.

- Test con errori di contesto: **0**
- Test resilienti: **0**
- Test falliti: **0**
- Test crashati: **0**
- Resilience rate: **0.00%**
- Occorrenze complessive: **0**

</details>

---

## 8. Dettaglio per test

> I log per ogni singolo test sono racchiusi in un blocco collassabile per evitare di sovraccaricare la lettura del documento.
> **Colonne principali:**
> - `Success`: il test è complessivamente superato (dominio corretto + piano non vuoto + eventuale replan applicato).
> - `Valid Plan`: il piano è strutturalmente valido (non vuoto e senza crash). *Nota: un piano può essere valido ma il test può fallire (es. dominio sbagliato).*
> - `Confidence`: punteggio di autovalutazione dell'agente (0-1).
> - `Val Attempts`: numero di iterazioni di correzione effettuate.
> - `Ctx Errors`: numero di errori riscontrati nelle chiamate a servizi esterni.
> - `Semantic`: punteggio qualitativo complessivo (da 1 a 5) assegnato dal giudice LLM.

<details>
<summary><strong>Espandi Tabella Completa dei Test</strong></summary>

| Test | Difficoltà | Target | Modello | Context | Expected Domain | Actual Domain | Success | Valid Plan | Confidence | Val Attempts | Ctx Errors | Semantic |
|:---|:---|:---|:---|:---|:---|:---|:---:|:---:|---:|---:|---:|---:|
| `routine_01` | easy | standard_planning | **dots-3-note-preview** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **dots-3-note-preview** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **dots-3-note-preview** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **dots-3-note-preview** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **dots-3-note-preview** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 3.40 |
| `travel_01` | easy | standard_planning | **dots-3-note-preview** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_02` | medium | vague_instructions | **dots-3-note-preview** | none | travel | travel | ✓ | ✓ | 0.75 | 1 | 0 | 5.00 |
| `travel_replan_01` | hard | replan_deletion | **dots-3-note-preview** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.40 |
| `unknown_01` | easy | standard_planning | **dots-3-note-preview** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **dots-3-note-preview** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **gemini-3.5-flash-lite** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **gemini-3.5-flash-lite** | none | routine | routine | ✓ | ✓ | 0.75 | 1 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **gemini-3.5-flash-lite** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **gemini-3.5-flash-lite** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **gemini-3.5-flash-lite** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 3.80 |
| `travel_01` | easy | standard_planning | **gemini-3.5-flash-lite** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.75 |
| `travel_02` | medium | vague_instructions | **gemini-3.5-flash-lite** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_replan_01` | hard | replan_deletion | **gemini-3.5-flash-lite** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `unknown_01` | easy | standard_planning | **gemini-3.5-flash-lite** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **gemini-3.5-flash-lite** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **gemini-3.6-flash** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **gemini-3.6-flash** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **gemini-3.6-flash** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **gemini-3.6-flash** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **gemini-3.6-flash** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 5.00 |
| `travel_01` | easy | standard_planning | **gemini-3.6-flash** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_02` | medium | vague_instructions | **gemini-3.6-flash** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_replan_01` | hard | replan_deletion | **gemini-3.6-flash** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `unknown_01` | easy | standard_planning | **gemini-3.6-flash** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **gemini-3.6-flash** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **gpt-oss-20b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **gpt-oss-20b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **gpt-oss-20b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **gpt-oss-20b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **gpt-oss-20b** | none | study | study | ✗ | ✗ | 0.00 | 3 | 0 | - |
| `travel_01` | easy | standard_planning | **gpt-oss-20b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_02` | medium | vague_instructions | **gpt-oss-20b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.00 |
| `travel_replan_01` | hard | replan_deletion | **gpt-oss-20b** | none | travel | travel | ✓ | ✓ | 0.75 | 1 | 0 | 2.60 |
| `unknown_01` | easy | standard_planning | **gpt-oss-20b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **gpt-oss-20b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **laguna-s-2.1** | none | routine | routine | ✓ | ✓ | 0.75 | 1 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **laguna-s-2.1** | none | routine | routine | ✓ | ✓ | 0.75 | 1 | 0 | 4.50 |
| `study_01` | easy | standard_planning | **laguna-s-2.1** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.50 |
| `study_02` | medium | vague_instructions | **laguna-s-2.1** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **laguna-s-2.1** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.20 |
| `travel_01` | easy | standard_planning | **laguna-s-2.1** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_02` | medium | vague_instructions | **laguna-s-2.1** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.50 |
| `travel_replan_01` | hard | replan_deletion | **laguna-s-2.1** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 3.40 |
| `unknown_01` | easy | standard_planning | **laguna-s-2.1** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **laguna-s-2.1** | none | unknown | study | ✗ | ✓ | 1.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **llama3.2** | none | routine | routine | ✓ | ✓ | 0.75 | 1 | 0 | 3.50 |
| `routine_02` | easy | standard_planning | **llama3.2** | none | routine | routine | ✓ | ✓ | 0.75 | 1 | 0 | 4.00 |
| `study_01` | easy | standard_planning | **llama3.2** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 3.50 |
| `study_02` | medium | vague_instructions | **llama3.2** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.75 |
| `study_replan_01` | medium | replan_shift | **llama3.2** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 3.40 |
| `travel_01` | easy | standard_planning | **llama3.2** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.75 |
| `travel_02` | medium | vague_instructions | **llama3.2** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.25 |
| `travel_replan_01` | hard | replan_deletion | **llama3.2** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.40 |
| `unknown_01` | easy | standard_planning | **llama3.2** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **llama3.2** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **ministral-3:3b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 4.00 |
| `routine_02` | easy | standard_planning | **ministral-3:3b** | none | routine | routine | ✗ | ✗ | 0.00 | 3 | 0 | - |
| `study_01` | easy | standard_planning | **ministral-3:3b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **ministral-3:3b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **ministral-3:3b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.20 |
| `travel_01` | easy | standard_planning | **ministral-3:3b** | none | travel | travel | ✓ | ✓ | 0.75 | 1 | 0 | 2.75 |
| `travel_02` | medium | vague_instructions | **ministral-3:3b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 3.25 |
| `travel_replan_01` | hard | replan_deletion | **ministral-3:3b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.60 |
| `unknown_01` | easy | standard_planning | **ministral-3:3b** | none | unknown | study | ✗ | ✗ | 0.00 | 3 | 0 | - |
| `unknown_02` | easy | standard_planning | **ministral-3:3b** | none | unknown | study | ✗ | ✓ | 1.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **nemotron-3-ultra-550b-a55b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **nemotron-3-ultra-550b-a55b** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 3.60 |
| `travel_01` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_02` | medium | vague_instructions | **nemotron-3-ultra-550b-a55b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `travel_replan_01` | hard | replan_deletion | **nemotron-3-ultra-550b-a55b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.20 |
| `unknown_01` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **nemotron-3-ultra-550b-a55b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **nemotron-3.5-lightning** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `routine_02` | easy | standard_planning | **nemotron-3.5-lightning** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_01` | easy | standard_planning | **nemotron-3.5-lightning** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_02` | medium | vague_instructions | **nemotron-3.5-lightning** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `study_replan_01` | medium | replan_shift | **nemotron-3.5-lightning** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 3.80 |
| `travel_01` | easy | standard_planning | **nemotron-3.5-lightning** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.25 |
| `travel_02` | medium | vague_instructions | **nemotron-3.5-lightning** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 4.25 |
| `travel_replan_01` | hard | replan_deletion | **nemotron-3.5-lightning** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 5.00 |
| `unknown_01` | easy | standard_planning | **nemotron-3.5-lightning** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **nemotron-3.5-lightning** | none | unknown | study | ✗ | ✓ | 1.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **qwen3:1.7b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 1.75 |
| `routine_02` | easy | standard_planning | **qwen3:1.7b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 2.75 |
| `study_01` | easy | standard_planning | **qwen3:1.7b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.00 |
| `study_02` | medium | vague_instructions | **qwen3:1.7b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 4.75 |
| `study_replan_01` | medium | replan_shift | **qwen3:1.7b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 3.20 |
| `travel_01` | easy | standard_planning | **qwen3:1.7b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 3.25 |
| `travel_02` | medium | vague_instructions | **qwen3:1.7b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 2.25 |
| `travel_replan_01` | hard | replan_deletion | **qwen3:1.7b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 3.40 |
| `unknown_01` | easy | standard_planning | **qwen3:1.7b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **qwen3:1.7b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `routine_01` | easy | standard_planning | **qwen3:4b** | none | routine | routine | ✓ | ✓ | 1.00 | 0 | 0 | 4.75 |
| `routine_02` | easy | standard_planning | **qwen3:4b** | none | routine | routine | ✗ | ✗ | 0.00 | 3 | 0 | - |
| `study_01` | easy | standard_planning | **qwen3:4b** | none | study | study | ✓ | ✓ | 0.50 | 2 | 0 | 4.25 |
| `study_02` | medium | vague_instructions | **qwen3:4b** | none | study | study | ✓ | ✓ | 0.75 | 1 | 0 | 4.50 |
| `study_replan_01` | medium | replan_shift | **qwen3:4b** | none | study | study | ✓ | ✓ | 1.00 | 0 | 0 | 3.40 |
| `travel_01` | easy | standard_planning | **qwen3:4b** | none | travel | travel | ✗ | ✗ | 0.00 | 3 | 0 | - |
| `travel_02` | medium | vague_instructions | **qwen3:4b** | none | travel | travel | ✓ | ✓ | 0.75 | 1 | 0 | 3.00 |
| `travel_replan_01` | hard | replan_deletion | **qwen3:4b** | none | travel | travel | ✓ | ✓ | 1.00 | 0 | 0 | 3.40 |
| `unknown_01` | easy | standard_planning | **qwen3:4b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |
| `unknown_02` | easy | standard_planning | **qwen3:4b** | none | unknown | unknown | ✓ | ✗ | 0.00 | 0 | 0 | - |

</details>