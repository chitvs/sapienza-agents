"""
Rendering del report in Markdown.

Prende in input il dizionario prodotto da aggregate.build_report() e
produce il testo del report leggibile da uomo. Nessun calcolo qui
dentro: solo formattazione. Logica invariata rispetto al vecchio
metrics.py, solo spostata in un modulo dedicato.
"""

from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fmt_score(value: float | None, green_th: float, yellow_th: float, reverse: bool = False, is_pct: bool = True) -> str:
    """Aggiunge un semaforo visivo in base alle soglie. 'reverse' serve se 'basso è meglio'."""
    if value is None:
        return "-"
    
    is_good = value <= green_th if reverse else value >= green_th
    is_ok = value <= yellow_th if reverse else value >= yellow_th
    
    icon = "🟢" if is_good else ("🟡" if is_ok else "🔴")
    suffix = "%" if is_pct else ""
    
    return f"{icon} {value:.2f}{suffix}"


def _markdown_kpi_table(report: dict[str, Any]) -> str:
    """Tabella 1: Solo le metriche di Esito (KPI Principali)"""
    rows = [
        "| Modello | Test | Supported Success | Domain Acc. | Intent Acc. (Supp) | Semantic Score | Crash Rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        rows.append(
            "| " + " | ".join([
                model_name,
                _fmt(metrics["n_test"]),
                _fmt_score(metrics["supported_success_rate"], 90, 70),
                _fmt_score(metrics["domain_accuracy"], 90, 70),
                _fmt_score(metrics["intent_accuracy"], 90, 70),
                _fmt_score(metrics["semantic"]["overall_score"], 4.0, 3.0, is_pct=False),
                _fmt_score(metrics["system_crash_rate"], 0.0, 5.0, reverse=True),
            ]) + " |"
        )
    return "\n".join(rows)


def _markdown_diagnostic_table(report: dict[str, Any]) -> str:
    """Tabella 2: Solo le metriche di Comportamento (Diagnostiche)"""
    rows = [
        "| Modello | Zero-shot | Recovery | Correction Failure | Val. Rate | Mean Val. (se err) | Context Errors | Overconfidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        rows.append(
            "| " + " | ".join([
                model_name,
                _fmt_score(metrics["zero_shot_rate"], 80, 50),
                _fmt_score(metrics["self_correction_recovery_rate"], 80, 50),
                _fmt_score(metrics["correction_failure_rate"], 10, 30, reverse=True),
                f"{metrics['validation_attempt_rate']:.2f}%",
                _fmt(metrics["mean_attempts_per_corrected_test"]),
                _fmt(metrics["average_context_errors"]),
                _fmt_score(metrics["overconfidence_rate"], 5, 15, reverse=True),
            ]) + " |"
        )
    return "\n".join(rows)


def _markdown_semantic_table(report: dict[str, Any]) -> str:
    rows = [
        "| Modello | Groundedness | Adherence | Feasibility | Granularity | Replanning | Overall | Coverage | Partial | Invalid scores |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        semantic = metrics["semantic"]
        dimensions = semantic["dimensions"]
        rows.append(
            "| " + " | ".join([
                model_name,
                _fmt(dimensions["groundedness"]["mean"]),
                _fmt(dimensions["semantic_adherence"]["mean"]),
                _fmt(dimensions["human_feasibility"]["mean"]),
                _fmt(dimensions["granularity"]["mean"]),
                _fmt(dimensions["replanning_consistency"]["mean"]),
                _fmt(semantic["overall_score"]),
                f"{semantic['coverage_rate']:.2f}%",
                str(semantic["partial_evaluations"]),
                str(semantic["invalid_score_values"]),
            ]) + " |"
        )
    return "\n".join(rows)


def _markdown_simple_table(groups: dict[str, Any]) -> str:
    rows = [
        "| Gruppo | Test | Supported Success | Domain Acc. | Intent Acc. (Supp) | Semantic | Crash |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, metrics in groups.items():
        rows.append(
            "| " + " | ".join([
                key,
                str(metrics["n_test"]),
                f"{metrics['supported_success_rate']:.2f}%",
                f"{metrics['domain_accuracy']:.2f}%",
                f"{metrics['intent_accuracy']:.2f}%",
                _fmt(metrics["semantic"]["overall_score"]),
                f"{metrics['system_crash_rate']:.2f}%",
            ]) + " |"
        )
    return "\n".join(rows)


def generate_markdown(report: dict[str, Any]) -> str:
    global_metrics = report["global"]
    insights = report.get("insights", {})

    lines = [
        "# Planner Agent Benchmark Report",
        "",
        f"Generated: `{report['metadata']['generated_at']}`",
        "",
        "> *Nota metodologica: Gli indicatori visivi (🟢 🟡 🔴) e le relative soglie sono euristiche pensate per facilitare la lettura comparativa rapida e non rappresentano validazioni statistiche assolute del modello.*",
        "",
        "## 1. Executive Summary & Insights",
        "",
    ]

    # --- SEZIONE TL;DR (INSIGHTS) ---
    if insights:
        best_perf = insights.get("best_performer", {})
        best_sem = insights.get("best_semantic", {})
        smooth = insights.get("smoothest_model", {})
        bottleneck = insights.get("top_bottleneck_error", {})

        lines.extend([
            "### 💡 TL;DR Insights",
            "",
            f"- 🏆 **Miglior Modello (Successo):** `{best_perf.get('model')}` con il **{best_perf.get('supported_success_rate', 0.0):.2f}%** di Supported Success.",
            f"- 🧠 **Miglior Qualità Semantica:** `{best_sem.get('model')}` con uno score di **{best_sem.get('overall_score') or 0.0:.2f}/5**.",
            f"- ⚡ **Esecuzione più Fluida:** `{smooth.get('model')}` (Zero-shot: {smooth.get('zero_shot_rate', 0.0):.2f}%, Val. Rate: {smooth.get('validation_attempt_rate', 0.0):.2f}%).",
            f"- 🚨 **Collo di Bottiglia:** L'errore di validazione più frequente è `{bottleneck.get('category')}` ({bottleneck.get('occurrences')} occorrenze).",
            f"- ♻️ **Spreco Computazionale:** Il **{insights.get('correction_failure_rate_global', 0.0):.2f}%** dei cicli di auto-correzione fallisce (Correction Failure Rate).",
            "",
        ])

    # --- KPI E DIAGNOSTICA GLOBALE ---
    lines.extend([
        "### 🎯 KPI Principali (L'esito)",
        "",
        f"- Supported Success Rate: **{_fmt_score(global_metrics['supported_success_rate'], 90, 70)}**",
        f"- Domain Accuracy: **{_fmt_score(global_metrics['domain_accuracy'], 90, 70)}**",
        f"- Intent Acc. (Supported): **{_fmt_score(global_metrics['intent_accuracy'], 90, 70)}**",
        f"- Semantic Overall Score: **{_fmt_score(global_metrics['semantic']['overall_score'], 4.0, 3.0, is_pct=False)} / 5**",
        f"- System Crash Rate: **{_fmt_score(global_metrics['system_crash_rate'], 0.0, 5.0, reverse=True)}**",
        "",
        "### 🩺 Metriche Diagnostiche (Il comportamento)",
        "",
        f"- Zero-shot Rate: **{global_metrics['zero_shot_rate']:.2f}%**",
        f"- Recovery Rate: **{global_metrics['self_correction_recovery_rate']:.2f}%**",
        f"- Correction Failure Rate: **{global_metrics['correction_failure_rate']:.2f}%**",
        f"- Validation Attempt Rate: **{global_metrics['validation_attempt_rate']:.2f}%**",
        f"- Mean Validation Attempts (sui corretti): **{global_metrics['mean_attempts_per_corrected_test']:.2f}**",
        f"- Context Errors (media): **{global_metrics['average_context_errors']:.2f}**",
        f"- External Resilience: **{global_metrics['external_failures']['resilience_rate']:.2f}%**",
        f"- Non-empty Plan Rate: **{global_metrics['non_empty_plan_rate']:.2f}%**",
        f"- Unknown Domain Accuracy: **{global_metrics['unknown_domain_accuracy']:.2f}%**",
        f"- Overconfidence Rate: **{global_metrics['overconfidence_rate']:.2f}%**",
        "",
        "## 2. Confronto tra modelli",
        "",
        "### A. KPI Principali",
        "",
        _markdown_kpi_table(report),
        "",
        "### B. Metriche Diagnostiche",
        "",
        _markdown_diagnostic_table(report),
        "",
        "## 3. Valutazione semantica",
        "",
        _markdown_semantic_table(report),
        "",
        "## 4. Breakdown per Dominio",
        "",
        _markdown_simple_table(report["by_domain"]),
        "",
        "## 5. Breakdown per Difficoltà",
        "",
        _markdown_simple_table(report["by_difficulty"]),
        "",
        "## 6. Breakdown per Test Target",
        "",
        _markdown_simple_table(report["by_test_target"]),
        "",
        "## 7. Breakdown per Intent",
        "",
    ])

    for intent, metrics in report["by_intent"].items():
        lines.extend([
            f"### {intent}",
            "",
            f"- Test: **{metrics['n_test']}**",
            f"- Supported Success Rate: **{metrics['supported_success_rate']:.2f}%**",
            f"- Domain Accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Intent Accuracy: **{metrics['intent_accuracy']:.2f}%**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- Crash rate: **{metrics['system_crash_rate']:.2f}%**",
            "",
        ])

    lines.extend([
        "## 8. Context gathering",
        "",
    ])

    for context_mode, metrics in report["by_context_mode"].items():
        lines.extend([
            f"### {context_mode}",
            "",
            f"- Test: **{metrics['n_test']}**",
            f"- Supported Success Rate: **{metrics['supported_success_rate']:.2f}%**",
            f"- Domain Accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Intent Accuracy: **{metrics['intent_accuracy']:.2f}%**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- External resilience: **{metrics['external_failures']['resilience_rate']:.2f}%**",
            f"- Crash rate: **{metrics['system_crash_rate']:.2f}%**",
            "",
        ])

    validation = global_metrics["validation_errors"]
    if validation["categories"]:
        lines.extend([
            "## 9. Validation errors",
            "",
            f"- Test con almeno un errore di validazione: **{validation['tests_with_validation_errors']}**",
            f"- Occorrenze complessive: **{validation['total_occurrences']}**",
            "",
            "| Categoria | Occorrenze | Test coinvolti | Recuperati |",
            "|---|---:|---:|---:|",
        ])
        for item in validation["categories"]:
            lines.append(
                "| " + " | ".join([
                    item["category"],
                    str(item["occurrences"]),
                    str(item["tests_affected"]),
                    str(item["recovered_tests"]),
                ]) + " |"
            )
        lines.append("")
        
    # --- MATRICE DI CONFUSIONE INTENTI ---
    intent_matrix = global_metrics.get("intent_confusion_matrix", {})
    if intent_matrix:
        all_actuals = sorted({act for ex in intent_matrix.values() for act in ex.keys()})
        header = "| Expected \\ Actual | " + " | ".join(all_actuals) + " |"
        sep = "|---|" + "|".join(["---:"] * len(all_actuals)) + "|"
        
        lines.extend([
            "## 10. Matrice di Confusione Intenti",
            "",
            header,
            sep
        ])
        for expected in sorted(intent_matrix.keys()):
            row = f"| **{expected}** | " + " | ".join([str(intent_matrix[expected].get(act, 0)) for act in all_actuals]) + " |"
            lines.append(row)
        lines.append("")

    lines.extend([
        "## 11. External context failures",
        "",
        f"- Test con errori di contesto: **{global_metrics['external_failures']['tests_with_context_errors']}**",
        f"- Test resilienti: **{global_metrics['external_failures']['resilient_tests']}**",
        f"- Test falliti: **{global_metrics['external_failures']['failed_tests']}**",
        f"- Test crashati: **{global_metrics['external_failures']['crashed_tests']}**",
        f"- Resilience rate: **{global_metrics['external_failures']['resilience_rate']:.2f}%**",
        f"- Occorrenze complessive: **{global_metrics['external_failures']['error_occurrences']}**",
        "",
        "## 12. Per-test details",
        "",
        "| Test | Difficoltà | Target | Modello | Context | Expected Intent | Actual Intent | Expected Domain | Actual Domain | Success | Valid Plan | Confidence | Val Attempts | Ctx Errors | Semantic |",
        "|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|",
    ])

    for test in report["tests"]:
        lines.append(
            "| " + " | ".join([
                test["test_id"],
                _fmt(test["difficulty"]),
                _fmt(test["test_target"]),
                test["model"],
                test["context_mode"],
                test["expected_intent"],
                str(test["actual_intent"]),
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

    lines.append("")

    return "\n".join(lines)