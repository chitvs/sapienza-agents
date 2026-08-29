"""
Rendering del report in Markdown.

Produce un report tecnico pulito, privo di emoji o euristiche visive superflue,
strutturato professionalmente con sezioni chiare in lingua italiana, tabelle
formattate ed elementi collassabili per migliorare la leggibilità e gestire grandi moli di dati.
"""

from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    """Formatta un valore generico in stringa, gestendo i valori nulli."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fmt_pct(value: float | None) -> str:
    """Formatta un valore float in percentuale con due decimali."""
    if value is None:
        return "-"
    return f"{value:.2f}%"


def _markdown_kpi_table(report: dict[str, Any]) -> str:
    """Genera la tabella Markdown dei KPI principali per modello."""
    rows = [
        "| Modello | Test | Successo Supportato | Accuratezza Dominio | Score Semantico | Tasso Crash |",
        "|:---|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        rows.append(
            f"| `{model_name}` | {metrics['n_test']} | {_fmt_pct(metrics['supported_success_rate'])} | "
            f"{_fmt_pct(metrics['domain_accuracy'])} | {_fmt(metrics['semantic']['overall_score'])} | "
            f"{_fmt_pct(metrics['system_crash_rate'])} |"
        )
    return "\n".join(rows)


def _markdown_diagnostic_table(report: dict[str, Any]) -> str:
    """Genera la tabella Markdown delle metriche diagnostiche e comportamentali."""
    rows = [
        "| Modello | Zero-shot | Recovery | Fallimento Correzione | Tasso Validazione | Media Validazioni | Errori Contesto | Overconfidence |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        rows.append(
            f"| `{model_name}` | {_fmt_pct(metrics['zero_shot_rate'])} | {_fmt_pct(metrics['self_correction_recovery_rate'])} | "
            f"{_fmt_pct(metrics['correction_failure_rate'])} | {_fmt_pct(metrics['validation_attempt_rate'])} | "
            f"{_fmt(metrics['mean_attempts_per_corrected_test'])} | {_fmt(metrics['average_context_errors'])} | "
            f"{_fmt_pct(metrics['overconfidence_rate'])} |"
        )
    return "\n".join(rows)


def _markdown_semantic_table(report: dict[str, Any]) -> str:
    """Genera la tabella Markdown di dettaglio per la valutazione semantica."""
    rows = [
        "| Modello | Groundedness | Aderenza | Fattibilità Umana | Granularità | Replanning | Overall | Copertura | Parziali | Non Validi |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        sem = metrics["semantic"]
        dim = sem["dimensions"]
        rows.append(
            f"| `{model_name}` | {_fmt(dim['groundedness']['mean'])} | {_fmt(dim['semantic_adherence']['mean'])} | "
            f"{_fmt(dim['human_feasibility']['mean'])} | {_fmt(dim['granularity']['mean'])} | "
            f"{_fmt(dim['replanning_consistency']['mean'])} | **{_fmt(sem['overall_score'])}** | "
            f"{_fmt_pct(sem['coverage_rate'])} | {sem['partial_evaluations']} | {sem['invalid_score_values']} |"
        )
    return "\n".join(rows)


def _markdown_simple_table(groups: dict[str, Any]) -> str:
    """Genera una tabella di aggregazione semplice (es. per dominio)."""
    rows = [
        "| Gruppo | Test | Successo Supportato | Accuratezza Dominio | Score Semantico | Tasso Crash |",
        "|:---|---:|---:|---:|---:|---:|",
    ]
    for key, metrics in groups.items():
        rows.append(
            f"| `{key}` | {metrics['n_test']} | {_fmt_pct(metrics['supported_success_rate'])} | "
            f"{_fmt_pct(metrics['domain_accuracy'])} | {_fmt(metrics['semantic']['overall_score'])} | "
            f"{_fmt_pct(metrics['system_crash_rate'])} |"
        )
    return "\n".join(rows)


def _markdown_model_cross_table(report: dict[str, Any], cross_key: str, title: str) -> str:
    """Genera una tabella incrociata tra modelli e categorie (difficoltà o target)."""
    data = report.get(cross_key, {})
    if not data:
        return f"*Nessun dato disponibile per {title}.*\n"
    
    all_groups = set()
    for model_data in data.values():
        all_groups.update(model_data.keys())
    all_groups = sorted([g for g in all_groups if g is not None and g != "none"])
    
    if not all_groups:
        return f"*Nessun gruppo definito per {title}.*\n"
    
    lines = [
        f"### {title}",
        "",
        f"| Modello | {' | '.join(all_groups)} |",
        "|:---|" + "|".join(["---:"] * len(all_groups)) + "|"
    ]
    
    for model in sorted(data.keys()):
        row = [f"`{model}`"]
        for group in all_groups:
            if group in data[model]:
                metrics = data[model][group]
                row.append(f"{_fmt_pct(metrics['supported_success_rate'])} ({metrics['n_test']})")
            else:
                row.append("-")
        lines.append("| " + " | ".join(row) + " |")
    
    lines.append("")
    return "\n".join(lines)


def generate_markdown(report: dict[str, Any]) -> str:
    """
    Costruisce e restituisce il documento Markdown completo in lingua italiana,
    strutturato con indice, sezioni logiche, callout e tabelle dettagliate racchiuse in blocchi collassabili.
    """
    global_metrics = report["global"]
    insights = report.get("insights", {})

    lines = [
        "# Valutazione dell'agente Planner",
        "",
        f"> **Data Generazione:** `{report['metadata']['generated_at']}`  ",
        f"> **Test Totali:** `{global_metrics['n_test']}`  ",
        f"> **Modelli Valutati:** `{len(report['metadata']['models'])}`",
        "",
        "## Indice dei contenuti",
        "- [1. Sintesi Esecutiva & Insights](#1-sintesi-esecutiva--insights)",
        "- [2. Confronto tra modelli](#2-confronto-tra-modelli)",
        "- [3. Valutazione semantica](#3-valutazione-semantica)",
        "- [4. Breakdown per Dominio](#4-breakdown-per-dominio)",
        "- [5. Breakdown per Difficoltà e Target](#5-breakdown-per-difficoltà-e-target)",
        "- [6. Context Gathering](#6-context-gathering)",
        "- [7. Errori di validazione e contesti esterni](#7-errori-di-validazione-e-contesti-esterni)",
        "- [8. Dettaglio per test](#8-dettaglio-per-test)",
        "",
        "---",
        "",
        "## 1. Sintesi Esecutiva & Insights",
        "",
    ]

    if insights:
        best_perf = insights.get("best_performer", {})
        best_sem = insights.get("best_semantic", {})
        smooth = insights.get("smoothest_model", {})
        bottleneck = insights.get("top_bottleneck_error", {})

        lines.extend([
            "> ### Sintesi dei risultati",
            "> ",
            f"> - **Top Performer (Successo):** `{best_perf.get('model')}` con il **{_fmt_pct(best_perf.get('supported_success_rate'))}** di Supported Success.",
            f"> - **Miglior Qualità Semantica:** `{best_sem.get('model')}` con uno score complessivo di **{_fmt(best_sem.get('overall_score'))} / 5**.",
            f"> - **Esecuzione più Fluida:** `{smooth.get('model')}` (Zero-shot: {_fmt_pct(smooth.get('zero_shot_rate'))}, Validation Rate: {_fmt_pct(smooth.get('validation_attempt_rate'))}).",
            f"> - **Collo di Bottiglia Principale:** L'errore di validazione più ricorrente è `{bottleneck.get('category')}` ({bottleneck.get('occurrences')} occorrenze).",
            f"> - **Spreco Computazionale:** Il **{_fmt_pct(insights.get('correction_failure_rate_global'))}** dei cicli di auto-correzione fallisce (Correction Failure Rate).",
            "",
        ])

    lines.extend([
        "<details>",
        "<summary><strong>Visualizza metriche globali (KPI e Diagnostica)</strong></summary>",
        "",
        "### KPI Globali",
        f"- Supported Success Rate: `{_fmt_pct(global_metrics['supported_success_rate'])}`",
        f"- Domain Accuracy: `{_fmt_pct(global_metrics['domain_accuracy'])}`",
        f"- Semantic Overall Score: `{_fmt(global_metrics['semantic']['overall_score'])} / 5`",
        f"- System Crash Rate: `{_fmt_pct(global_metrics['system_crash_rate'])}`",
        "",
        "### Metriche Diagnostiche",
        f"- Zero-shot Rate: `{_fmt_pct(global_metrics['zero_shot_rate'])}`",
        f"- Recovery Rate: `{_fmt_pct(global_metrics['self_correction_recovery_rate'])}`",
        f"- Correction Failure Rate: `{_fmt_pct(global_metrics['correction_failure_rate'])}`",
        f"- Validation Attempt Rate: `{_fmt_pct(global_metrics['validation_attempt_rate'])}`",
        f"- Mean Validation Attempts (sui corretti): `{_fmt(global_metrics['mean_attempts_per_corrected_test'])}`",
        f"- Context Errors (media): `{_fmt(global_metrics['average_context_errors'])}`",
        f"- External Resilience: `{_fmt_pct(global_metrics['external_failures']['resilience_rate'])}`",
        f"- Non-empty Plan Rate: `{_fmt_pct(global_metrics['non_empty_plan_rate'])}`",
        f"- Unknown Domain Accuracy: `{_fmt_pct(global_metrics['unknown_domain_accuracy'])}`",
        f"- Overconfidence Rate: `{_fmt_pct(global_metrics['overconfidence_rate'])}`",
        "",
        "</details>",
        "",
        "---",
        "",
        "## 2. Confronto tra modelli",
        "",
        "> **Spiegazione delle metriche (KPI):**",
        "> - **Successo Supportato**: percentuale di test superati nei domini supportati (esclude i casi 'unknown' fuori scope).",
        "> - **Accuratezza Dominio**: correttezza della classificazione del dominio (es. 'study' riconosciuto come 'study').",
        "> - **Score Semantico**: valutazione qualitativa da LLM-as-a-judge, su una scala da 1 a 5 (più alto è meglio).",
        "> - **Tasso Crash**: test terminati con eccezioni o errori di sistema.",
        "",
        "### KPI Principali",
        _markdown_kpi_table(report),
        "",
        "> **Spiegazione delle metriche (Diagnostiche):**",
        "> - **Zero-shot**: test superati al primo tentativo, senza bisogno di correzioni (massima efficienza).",
        "> - **Recovery**: tra i test che hanno richiesto correzione, percentuale di quelli che sono infine riusciti.",
        "> - **Fallimento Correzione**: percentuale di cicli di correzione che falliscono (spreco computazionale).",
        "> - **Tasso Validazione**: test che hanno innescato almeno un errore di validazione strutturale.",
        "> - **Media Validazioni**: numero medio di tentativi di correzione *solo sui test che hanno avuto errori*.",
        "> - **Errori Contesto**: numero medio di fallimenti nelle chiamate a servizi esterni (API, KG, ecc.).",
        "> - **Overconfidence**: percentuale di test falliti in cui l'agente aveva comunque una confidenza ≥ 0.8 (segnale di allucinazione).",
        "",
        "### Metriche Diagnostiche",
        _markdown_diagnostic_table(report),
        "",
        "---",
        "",
        "## 3. Valutazione semantica",
        "",
        "> **Cosa misurano le dimensioni semantiche (1-5):**",
        "> - **Groundedness**: il piano è ancorato al contesto fornito (orari, date, vincoli)?",
        "> - **Aderenza**: risponde esattamente alla richiesta dell'utente?",
        "> - **Fattibilità Umana**: è realistico e sostenibile per un essere umano?",
        "> - **Granularità**: il livello di dettaglio è appropriato (né troppo vago, né troppo minuzioso)?",
        "> - **Replanning**: nel caso di modifica di un piano esistente, mantiene coerenza con l'originale?",
        "> - **Overall**: media aritmetica delle dimensioni valutate (solo se almeno 3 dimensioni sono disponibili).",
        "> - **Copertura**: percentuale di test eleggibili che sono stati effettivamente valutati semanticamente.",
        "",
        _markdown_semantic_table(report),
        "",
        "---",
        "",
        "## 4. Breakdown per Dominio",
        "",
        "> I dati sono aggregati per dominio atteso (`study`, `travel`, `routine`, `unknown`). ",
        "> Questo permette di capire se l'agente performa meglio su alcune tipologie di richieste.",
        "",
        _markdown_simple_table(report["by_domain"]),
        "",
        "---",
        "",
        "## 5. Breakdown per Difficoltà e Target",  
        "",
        "> **Difficoltà:** `easy`, `medium`, `hard`. I target più complessi includono `time_math` (calcoli temporali), ",
        "> `impossible_schedule` (richieste irrealizzabili) e `replan_deletion` (modifiche strutturali).",
        "> Le celle mostrano: **Supported Success Rate** e, tra parentesi, il numero di test in quel gruppo.",
        "",
        _markdown_model_cross_table(report, "by_model_and_difficulty", "Supported Success Rate per Modello e Difficoltà"),
        _markdown_model_cross_table(report, "by_model_and_test_target", "Supported Success Rate per Modello e Test Target"),
        "",
        "---",
        "",
        "## 6. Context gathering",
        "",
        "> **Modalità testate:**",
        "> - `deterministic`: usa una lista fissa di tool (es. kg_agent, multiapi_agent) definita a priori.",
        "> - `react`: l'agente decide iterativamente quali tool chiamare in base al contesto.",
        "> - `none`: nessun recupero di contesto esterno (solo ragionamento interno).",
        "> La metrica *External Resilience* indica la percentuale di test che, nonostante errori nelle chiamate esterne, ",
        "> sono comunque riusciti a produrre un piano valido.",
        "",
    ])

    for context_mode, metrics in report["by_context_mode"].items():
        lines.extend([
            f"### Modalità: `{context_mode}`",
            "",
            f"- Test valutati: **{metrics['n_test']}**",
            f"- Supported Success Rate: **{_fmt_pct(metrics['supported_success_rate'])}**",
            f"- Domain Accuracy: **{_fmt_pct(metrics['domain_accuracy'])}**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- External resilience: **{_fmt_pct(metrics['external_failures']['resilience_rate'])}**",
            f"- Crash rate: **{_fmt_pct(metrics['system_crash_rate'])}**",
            "",
        ])

    lines.extend(["---", "", "## 7. Errori di validazione e contesti esterni", ""])

    validation = global_metrics["validation_errors"]
    if validation["categories"]:
        lines.extend([
            "<details>",
            "<summary><strong>Dettaglio errori di validazione logica</strong></summary>",
            "",
            "> **Cosa sono:** errori sollevati dal validatore strutturale quando il piano non rispetta lo schema JSON ",
            "> o le regole logiche (es. orari sovrapposti, `duration_minutes` non numerico, giorno mancante).",
            "> **Recuperati** = test che, dopo aver ricevuto questi errori, sono comunque riusciti a produrre un piano valido.",
            "",
            "> **Legenda delle categorie di errore:**",
            "> | Codice errore | Significato |",
            "> |:---|:---|",
            "> | `draft_vuoto_o_non_json` | Il piano restituito è vuoto o non è un JSON valido. |",
            "> | `campo_title_mancante` | Manca il campo obbligatorio `title` del piano. |",
            "> | `campo_summary_tipo_errato` | Il campo `summary` non è una stringa valida. |",
            "> | `campo_contingency_notes_tipo_errato` | Il campo `contingency_notes` non è una lista di stringhe. |",
            "> | `days_mancante_o_vuoto` | Il campo `days` (elenco dei giorni) è mancante o vuoto. |",
            "> | `day_index_non_valido` | L'indice del giorno (`day_index`) non è un numero intero valido. |",
            "> | `day_index_duplicato` | Due giorni consecutivi hanno lo stesso `day_index`. |",
            "> | `campo_label_tipo_errato` | Il campo `label` (etichetta del giorno) non è una stringa. |",
            "> | `formato_data_invalido` | Il campo `date` non rispetta il formato `YYYY-MM-DD`. |",
            "> | `slots_mancanti_o_invalidi` | La lista `slots` è mancante, vuota o malformata. |",
            "> | `campo_task_mancante` | Manca il campo obbligatorio `task` in uno slot. |",
            "> | `campo_category_tipo_errato` | Il campo `category` non è tra quelli ammessi (`studio`, `visita`, `pasto`, ...). |",
            "> | `campo_subtasks_tipo_errato` | Il campo `subtasks` non è una lista di stringhe. |",
            "> | `campo_notes_tipo_errato` | Il campo `notes` non è una stringa valida. |",
            "> | `duration_minutes_non_valido` | La durata (`duration_minutes`) non è un numero positivo. |",
            "> | `formato_orario_invalido` | L'orario (`start_time`) non rispetta il formato `HH:MM`. |",
            "> | `durata_totale_giornaliera_eccessiva` | La somma delle durate degli slot in un singolo giorno supera le 24 ore. |",
            "> | `sovrapposizione_orari` | Due o più slot nello stesso giorno si sovrappongono temporalmente. |",
            "> | `routine_giorni_incompleti` | Per il dominio `routine`, mancano alcuni giorni della settimana (devono esserci tutti, 1-7). |",
            "> | `day_index_non_contiguo` | I `day_index` non formano una sequenza numerica contigua (es. 1, 2, 4). |",
            "> | `replan_non_effettuato` | Nel caso di `replan`, il piano finale è identico a quello precedente. |",
            "> | `altro` | Categoria di errore non riconosciuta dalle regex del validatore. |",
            "",
            f"- **Test con almeno un errore di validazione:** {validation['tests_with_validation_errors']}",
            f"- **Occorrenze complessive:** {validation['total_occurrences']}",
            "",
            "| Categoria | Occorrenze | Test coinvolti | Recuperati |",
            "|:---|---:|---:|---:|",
        ])
        for item in validation["categories"]:
            lines.append(
                f"| `{item['category']}` | {item['occurrences']} | {item['tests_affected']} | {item['recovered_tests']} |"
            )
        lines.extend(["", "</details>", ""])

    ext_failures = global_metrics['external_failures']
    lines.extend([
        "<details>",
        "<summary><strong>Dettaglio fallimenti contesto esterno</strong></summary>",
        "",
        "> **Cosa sono:** errori che si verificano durante la raccolta di informazioni da servizi esterni ",
        "> (es. API meteo, orari di apertura, Knowledge Graph). Un test è *resiliente* se, nonostante questi errori, ",
        "> riesce comunque a completare il piano senza crash.",
        "",
        f"- Test con errori di contesto: **{ext_failures['tests_with_context_errors']}**",
        f"- Test resilienti: **{ext_failures['resilient_tests']}**",
        f"- Test falliti: **{ext_failures['failed_tests']}**",
        f"- Test crashati: **{ext_failures['crashed_tests']}**",
        f"- Resilience rate: **{_fmt_pct(ext_failures['resilience_rate'])}**",
        f"- Occorrenze complessive: **{ext_failures['error_occurrences']}**",
        "",
        "</details>",
        "",
        "---",
        "",
        "## 8. Dettaglio per test",
        "",
        "> I log per ogni singolo test sono racchiusi in un blocco collassabile per evitare di sovraccaricare la lettura del documento.",
        "> **Colonne principali:**",
        "> - `Success`: il test è complessivamente superato (dominio corretto + piano non vuoto + eventuale replan applicato).",
        "> - `Valid Plan`: il piano è strutturalmente valido (non vuoto e senza crash). *Nota: un piano può essere valido ma il test può fallire (es. dominio sbagliato).*",
        "> - `Confidence`: punteggio di autovalutazione dell'agente (0-1).",
        "> - `Val Attempts`: numero di iterazioni di correzione effettuate.",
        "> - `Ctx Errors`: numero di errori riscontrati nelle chiamate a servizi esterni.",
        "> - `Semantic`: punteggio qualitativo complessivo (da 1 a 5) assegnato dal giudice LLM.",
        "",
        "<details>",
        "<summary><strong>Espandi Tabella Completa dei Test</strong></summary>",
        "",
        "| Test | Difficoltà | Target | Modello | Context | Expected Domain | Actual Domain | Success | Valid Plan | Confidence | Val Attempts | Ctx Errors | Semantic |",
        "|:---|:---|:---|:---|:---|:---|:---|:---:|:---:|---:|---:|---:|---:|",
    ])

    for test in report["tests"]:
        lines.append(
            "| " + " | ".join([
                f"`{test['test_id']}`",
                _fmt(test["difficulty"]),
                _fmt(test["test_target"]),
                f"**{test['model']}**",
                test["context_mode"],
                test["expected_domain"],
                str(test["actual_domain"]),
                "✓" if test["success"] else "✗",
                "✓" if test["valid_plan"] else "✗",
                _fmt(test["confidence"]),
                str(test["validation_attempts"]),
                str(test["context_error_count"]),
                _fmt(test["semantic"]["overall"]),
            ]) + " |"
        )

    lines.extend(["", "</details>", ""])

    return "\n".join(lines)