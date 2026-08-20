"""
Aggregazione dei TestOutcome in un report strutturato.

build_report() è il punto di ingresso principale: normalizza i record
grezzi in TestOutcome, applica le metriche di analytics.py a livello
globale e per ogni breakdown (modello, dominio, difficoltà, ...) e
restituisce un dizionario puro, pronto per essere serializzato in JSON
o passato al layer di presentazione (report_md.py). Nessuna funzione
di questo modulo tocca il filesystem.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .analytics import (
    _semantic_overall,
    _semantic_scores,
    avg_confidence,
    avg_confidence_non_crashed,
    domain_accuracy,
    intent_accuracy,
    intent_confusion_matrix,
    non_empty_plan_rate,
    external_failure_metrics,
    first_try_pass_rate,
    self_correction_recovery_rate,
    correction_failure_rate,
    semantic_metrics,
    success_rate,
    supported_success_rate,
    system_crash_rate,
    unknown_domain_accuracy,
    validation_error_metrics,
    validation_attempt_rate,
    mean_attempts_per_corrected_test,
    average_context_errors,
    overconfidence_rate,
)
from .model import TestOutcome, normalize


def _aggregate_outcomes(outcomes: list[TestOutcome]) -> dict[str, Any]:
    return {
        "n_test": len(outcomes),

        # Metriche principali
        "success_rate": success_rate(outcomes),
        "supported_success_rate": supported_success_rate(outcomes),
        "domain_accuracy": domain_accuracy(outcomes),
        "intent_accuracy": intent_accuracy(outcomes),
        "intent_confusion_matrix": intent_confusion_matrix(outcomes),
        "unknown_domain_accuracy": unknown_domain_accuracy(outcomes),
        "non_empty_plan_rate": non_empty_plan_rate(outcomes),

        # Pipeline / correzione
        "zero_shot_rate": first_try_pass_rate(outcomes),
        "self_correction_recovery_rate": self_correction_recovery_rate(outcomes),
        "correction_failure_rate": correction_failure_rate(outcomes),
        "system_crash_rate": system_crash_rate(outcomes),
        "validation_attempt_rate": validation_attempt_rate(outcomes),
        "mean_attempts_per_corrected_test": mean_attempts_per_corrected_test(outcomes),
        "average_context_errors": average_context_errors(outcomes),
        "overconfidence_rate": overconfidence_rate(outcomes),

        # Confidence
        "confidence_mean_successes": avg_confidence(outcomes),
        "confidence_mean_non_crashed": avg_confidence_non_crashed(outcomes),

        # Diagnostica
        "validation_errors": validation_error_metrics(outcomes),
        "external_failures": external_failure_metrics(outcomes),

        # Qualità semantica
        "semantic": semantic_metrics(outcomes),
    }


def _group_by(outcomes: list[TestOutcome], attribute: str) -> dict[str, list[TestOutcome]]:
    groups: defaultdict[str, list[TestOutcome]] = defaultdict(list)

    for outcome in outcomes:
        value = getattr(outcome, attribute, "unknown")
        groups[str(value)].append(outcome)

    return dict(groups)


def _aggregate_groups(outcomes: list[TestOutcome], attribute: str) -> dict[str, Any]:
    groups = _group_by(outcomes, attribute)

    return {
        key: _aggregate_outcomes(sorted(group, key=lambda outcome: outcome.test_id))
        for key, group in sorted(groups.items())
    }


def _test_detail(outcome: TestOutcome) -> dict[str, Any]:
    semantic_scores = _semantic_scores(outcome.semantic_evaluation)
    validation_attempts = len(outcome.validation_errors_history)
    context_errors = len(outcome.context_errors)

    return {
        "test_id": outcome.test_id,
        "difficulty": outcome.difficulty,
        "test_target": outcome.test_target,
        "model": outcome.model_name,
        "context_mode": outcome.context_mode,
        "intent": outcome.expected_intent,
        "expected_intent": outcome.expected_intent,
        "actual_intent": outcome.actual_intent,
        "expected_domain": outcome.expected_domain,
        "actual_domain": outcome.actual_domain,
        "success": outcome.success,
        "domain_correct": outcome.domain_correct,
        "crashed": outcome.crashed,
        "plan_is_empty": outcome.plan_is_empty,
        "valid_plan": outcome.valid_plan,
        "confidence": outcome.confidence,
        "validation_attempts": validation_attempts,
        "context_error_count": context_errors,
        "semantic": {
            **semantic_scores,
            "overall": _semantic_overall(outcome.semantic_evaluation),
        },
    }


def _generate_insights(
    global_metrics: dict[str, Any],
    by_model: dict[str, Any],
) -> dict[str, Any]:
    if not by_model:
        return {}

    # 1. Modello con il miglior Supported Success Rate (a parità, vince chi ha più Zero-shot)
    best_success_model, best_success_data = max(
        by_model.items(),
        key=lambda item: (item[1]["supported_success_rate"], item[1]["zero_shot_rate"]),
    )

    # 2. Modello con il punteggio Semantico più alto
    semantic_models = [
        (model, data) for model, data in by_model.items() if data["semantic"]["overall_score"] is not None
    ]
    best_semantic_model, best_semantic_score = (
        max(semantic_models, key=lambda item: item[1]["semantic"]["overall_score"])
        if semantic_models else (None, None)
    )

    # 3. Modello più fluido (Massimo zero-shot, a parità minima % di test che richiedono validazione)
    smoothest_model, smoothest_data = max(
        by_model.items(),
        key=lambda item: (item[1]["zero_shot_rate"], -item[1]["validation_attempt_rate"]),
    )

    # 4. Errore di validazione più frequente
    val_categories = global_metrics.get("validation_errors", {}).get("categories", [])
    top_error_category = val_categories[0]["category"] if val_categories else None
    top_error_occurrences = val_categories[0]["occurrences"] if val_categories else 0

    return {
        "best_performer": {
            "model": best_success_model,
            "supported_success_rate": best_success_data["supported_success_rate"],
        },
        "best_semantic": {
            "model": best_semantic_model,
            "overall_score": best_semantic_score["semantic"]["overall_score"] if best_semantic_score else None,
        },
        "smoothest_model": {
            "model": smoothest_model,
            "zero_shot_rate": smoothest_data["zero_shot_rate"],
            "validation_attempt_rate": smoothest_data["validation_attempt_rate"],
        },
        "top_bottleneck_error": {
            "category": top_error_category,
            "occurrences": top_error_occurrences,
        },
        "correction_failure_rate_global": global_metrics.get("correction_failure_rate", 0.0),
    }


def build_report(
    records: list[dict[str, Any]],
    semantic_evaluations: dict[str, Any] | None = None,
    dataset: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

    semantic_evaluations = semantic_evaluations or {}
    dataset_map = {item["id"]: item for item in dataset} if dataset else {}

    outcomes = [
        normalize(record, semantic_evaluations, dataset_map)
        for record in records
    ]

    global_metrics = _aggregate_outcomes(outcomes)
    by_model_metrics = _aggregate_groups(outcomes, "model_name")

    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_tests": len(dataset) if dataset is not None else None,
            "benchmark_records": len(records),
            "models": sorted({outcome.model_name for outcome in outcomes}),
            "context_modes": sorted({outcome.context_mode for outcome in outcomes}),
            "intents": sorted({outcome.expected_intent for outcome in outcomes}),
            "domains": sorted({outcome.expected_domain for outcome in outcomes}),
        },
        "insights": _generate_insights(global_metrics, by_model_metrics), 
        "global": global_metrics,
        "by_model": by_model_metrics,
        "by_context_mode": _aggregate_groups(outcomes, "context_mode"),
        "by_domain": _aggregate_groups(outcomes, "expected_domain"),
        "by_intent": _aggregate_groups(outcomes, "expected_intent"),
        "by_difficulty": _aggregate_groups(outcomes, "difficulty"),
        "by_test_target": _aggregate_groups(outcomes, "test_target"),
        "by_model_and_context": {},
        "tests": [
            _test_detail(outcome)
            for outcome in sorted(
                outcomes,
                key=lambda item: (
                    item.model_name,
                    item.context_mode,
                    item.test_id,
                ),
            )
        ],
    }

    # --------------------------------------------------------------------------
    # MODEL + CONTEXT
    # --------------------------------------------------------------------------

    model_context_groups: defaultdict[tuple[str, str], list[TestOutcome]] = defaultdict(list)

    for outcome in outcomes:
        model_context_groups[(outcome.model_name, outcome.context_mode)].append(outcome)

    for (model_name, context_mode), grouped in sorted(model_context_groups.items()):
        if model_name not in report["by_model_and_context"]:
            report["by_model_and_context"][model_name] = {}

        report["by_model_and_context"][model_name][context_mode] = _aggregate_outcomes(grouped)

    return report