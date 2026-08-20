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


def _markdown_model_table(report: dict[str, Any]) -> str:
    rows = [
        "| Modello | Test | Successo | Supported Success | Domain Acc. | Unknown Acc. | Valid Plan | Zero-shot | Recovery | Semantic | Crash |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for model_name, metrics in report["by_model"].items():
        rows.append(
            "| " + " | ".join([
                model_name,
                _fmt(metrics["n_test"]),
                f"{metrics['success_rate']:.2f}%",
                f"{metrics['supported_success_rate']:.2f}%",
                f"{metrics['domain_accuracy']:.2f}%",
                f"{metrics['unknown_domain_accuracy']:.2f}%",
                f"{metrics['valid_plan_rate']:.2f}%",
                f"{metrics['zero_shot_rate']:.2f}%",
                f"{metrics['self_correction_recovery_rate']:.2f}%",
                _fmt(metrics["semantic"]["overall_score"]),
                f"{metrics['system_crash_rate']:.2f}%",
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
        "| Gruppo | Test | Successo | Supported Success | Domain Accuracy | Valid Plan | Semantic | Crash |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for key, metrics in groups.items():
        rows.append(
            "| " + " | ".join([
                key,
                str(metrics["n_test"]),
                f"{metrics['success_rate']:.2f}%",
                f"{metrics['supported_success_rate']:.2f}%",
                f"{metrics['domain_accuracy']:.2f}%",
                f"{metrics['valid_plan_rate']:.2f}%",
                _fmt(metrics["semantic"]["overall_score"]),
                f"{metrics['system_crash_rate']:.2f}%",
            ]) + " |"
        )

    return "\n".join(rows)


def generate_markdown(report: dict[str, Any]) -> str:
    global_metrics = report["global"]

    lines = [
        "# Planner Agent Benchmark Report",
        "",
        f"Generated: `{report['metadata']['generated_at']}`",
        "",
        "## 1. Executive Summary",
        "",
        f"- Test eseguiti: **{global_metrics['n_test']}**",
        f"- Success rate: **{global_metrics['success_rate']:.2f}%**",
        f"- Supported-domain success rate: **{global_metrics['supported_success_rate']:.2f}%**",
        f"- Domain accuracy: **{global_metrics['domain_accuracy']:.2f}%**",
        f"- Unknown-domain accuracy: **{global_metrics['unknown_domain_accuracy']:.2f}%**",
        f"- Valid plan rate: **{global_metrics['valid_plan_rate']:.2f}%**",
        f"- Empty plan rate: **{global_metrics['empty_plan_rate']:.2f}%**",
        f"- Zero-shot rate: **{global_metrics['zero_shot_rate']:.2f}%**",
        f"- Self-correction recovery: **{global_metrics['self_correction_recovery_rate']:.2f}%**",
        f"- Final failure rate: **{global_metrics['final_failure_rate']:.2f}%**",
        f"- Crash rate: **{global_metrics['system_crash_rate']:.2f}%**",
        f"- Confidence media (sui successi): **{global_metrics['confidence_mean_successes']:.3f}**",
        f"- Confidence media (risultati non-crashati): **{global_metrics['confidence_mean_non_crashed']:.3f}**",
        f"- Semantic score: **{_fmt(global_metrics['semantic']['overall_score'])} / 5**",
        f"- Semantic coverage: **{global_metrics['semantic']['coverage_rate']:.2f}%**",
        "",
        "## 2. Confronto tra modelli",
        "",
        _markdown_model_table(report),
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
    ]

    for intent, metrics in report["by_intent"].items():
        lines.extend([
            f"### {intent}",
            "",
            f"- Test: **{metrics['n_test']}**",
            f"- Success rate: **{metrics['success_rate']:.2f}%**",
            f"- Supported-domain success rate: **{metrics['supported_success_rate']:.2f}%**",
            f"- Domain accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Valid plan rate: **{metrics['valid_plan_rate']:.2f}%**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- Semantic coverage: **{metrics['semantic']['coverage_rate']:.2f}%**",
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
            f"- Success rate: **{metrics['success_rate']:.2f}%**",
            f"- Supported-domain success rate: **{metrics['supported_success_rate']:.2f}%**",
            f"- Domain accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Valid plan rate: **{metrics['valid_plan_rate']:.2f}%**",
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

    lines.extend([
        "## 10. External context failures",
        "",
        f"- Test con errori di contesto: **{global_metrics['external_failures']['tests_with_context_errors']}**",
        f"- Test resilienti: **{global_metrics['external_failures']['resilient_tests']}**",
        f"- Test falliti: **{global_metrics['external_failures']['failed_tests']}**",
        f"- Test crashati: **{global_metrics['external_failures']['crashed_tests']}**",
        f"- Resilience rate: **{global_metrics['external_failures']['resilience_rate']:.2f}%**",
        f"- Occorrenze complessive: **{global_metrics['external_failures']['error_occurrences']}**",
        "",
        "## 11. Per-test details",
        "",
        "| Test | Difficoltà | Target | Modello | Context | Intent | Expected | Actual | Success | Valid Plan | Confidence | Attempts | Context Errors | Semantic |",
        "|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|",
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