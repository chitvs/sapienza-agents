"""
Modello dati del benchmark e normalizzazione dei record grezzi.

Contiene il dataclass TestOutcome (rappresentazione in memoria di un
singolo test eseguito) e la funzione normalize() che lo costruisce a
partire da un record grezzo di benchmark_results.json, dalle valutazioni
semantiche e dal dataset di riferimento. Nessuna funzione di questo
modulo tocca il filesystem: è testabile passando solo dizionari.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class TestOutcome:
    test_id: str
    model_name: str
    context_mode: str
    expected_intent: str
    expected_domain: str
    actual_domain: str | None
    actual_intent: str | None

    success: bool
    crashed: bool

    plan_is_empty: bool
    domain_correct: bool
    valid_plan: bool

    confidence: float

    validation_errors_history: list[list[str]]
    context_errors: list[str]

    semantic_evaluation: dict[str, Any] | None
    difficulty: str | None = None
    test_target: str | None = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Converte un valore in float in modo difensivo.

    Valori non numerici, NaN e inf vengono considerati non validi e
    sostituiti dal default.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    return result if math.isfinite(result) else default


# ==============================================================================
# ERRORI DI CONTESTO
# ==============================================================================

def _extract_context_errors(record: dict[str, Any]) -> list[str]:
    plan_output = record.get("plan_output") or {}
    return list(plan_output.get("context_errors") or [])


def normalize(
    record: dict[str, Any],
    semantic_evaluations: dict[str, Any],
    dataset_map: dict[str, Any],
) -> TestOutcome:

    plan_output = record.get("plan_output") or {}
    days = plan_output.get("days") or []

    test_id = record["test_id"]
    test_info = dataset_map.get(test_id, {})

    model_name = record["model_name"]
    context_mode = record.get("context_gathering_mode", "unknown")

    expected_intent = record.get("expected_intent", "new_plan")
    expected_domain = record["expected_domain"]
    actual_domain = plan_output.get("domain")
    is_replanned = plan_output.get("replanned")
    if is_replanned is True:
        actual_intent = "replan"
    elif is_replanned is False:
        actual_intent = "new_plan"
    else:
        actual_intent = "missing"

    crashed = record.get("error") is not None
    plan_is_empty = len(days) == 0

    domain_correct = (
        not crashed
        and actual_domain == expected_domain
    )

    # "valid_plan" rappresenta un piano finale strutturalmente utilizzabile:
    # - nessun crash
    # - almeno un giorno presente
    #
    # La correttezza rispetto al dominio viene mantenuta separata in
    # "domain_correct" e quella rispetto all'intero test in "success".
    valid_plan = (
        not crashed
        and not plan_is_empty
    )

    result_key = f"{test_id}::{model_name}::{context_mode}"
    semantic_evaluation = semantic_evaluations.get(result_key)

    return TestOutcome(
        test_id=test_id,
        model_name=model_name,
        context_mode=context_mode,
        expected_intent=expected_intent,
        expected_domain=expected_domain,
        actual_domain=actual_domain,
        actual_intent=actual_intent,

        success=bool(record.get("success")),
        crashed=crashed,

        plan_is_empty=plan_is_empty,
        domain_correct=domain_correct,
        valid_plan=valid_plan,

        confidence=_safe_float(plan_output.get("confidence", 0.0)),

        validation_errors_history=record.get("validation_errors_history") or [],
        context_errors=_extract_context_errors(record),

        semantic_evaluation=semantic_evaluation,
        difficulty=test_info.get("difficulty"),
        test_target=test_info.get("test_target"),
    )