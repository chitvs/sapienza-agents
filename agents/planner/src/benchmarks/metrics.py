"""
Metriche e report finale per il benchmark del Planner Agent.

Legge:
    - benchmark_dataset.json
    - benchmark_results.json
    - semantic_eval_results.json

Produce:
    - benchmark_report.json
    - benchmark_report.md
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


# ==============================================================================
# PATH
# ==============================================================================

BENCHMARK_DIR = Path(__file__).resolve().parent

DATASET_PATH = BENCHMARK_DIR / "benchmark_dataset.json"
RESULTS_PATH = BENCHMARK_DIR / "benchmark_results.json"
SEMANTIC_RESULTS_PATH = BENCHMARK_DIR / "semantic_eval_results.json"

REPORT_JSON_PATH = BENCHMARK_DIR / "benchmark_report.json"
REPORT_MD_PATH = BENCHMARK_DIR / "benchmark_report.md"


# ==============================================================================
# MODELLI DATI
# ==============================================================================

@dataclass
class TestOutcome:
    test_id: str
    model_name: str
    context_mode: str
    expected_intent: str
    expected_domain: str
    actual_domain: str | None

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


# ==============================================================================
# UTILITY
# ==============================================================================

def _pct(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return default

    return json.loads(content)


# ==============================================================================
# ERRORI DI CONTESTO
# ==============================================================================

_CONTEXT_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(kg-agent|multiapi-agent): "
        r"(timeout dopo|errore HTTP|errore di connessione|errore imprevisto)"
    ),
    re.compile(r"^gather_context_react: "),
    re.compile(r"^tool sconosciuto: "),
)


def _extract_context_errors(record: dict[str, Any]) -> list[str]:
    plan_output = record.get("plan_output") or {}

    if "context_errors" in plan_output:
        return list(plan_output.get("context_errors") or [])

    notes: list[str] = plan_output.get("contingency_notes") or []

    return [
        note
        for note in notes
        if any(pattern.match(note) for pattern in _CONTEXT_ERROR_PATTERNS)
    ]


# ==============================================================================
# NORMALIZZAZIONE
# ==============================================================================

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

    crashed = record.get("error") is not None
    plan_is_empty = len(days) == 0

    domain_correct = (
        not crashed
        and actual_domain == expected_domain
    )

    valid_plan = (
        not crashed
        and (
            expected_domain == "unknown"
            or not plan_is_empty
        )
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

        success=bool(record.get("success")),
        crashed=crashed,

        plan_is_empty=plan_is_empty,
        domain_correct=domain_correct,
        valid_plan=valid_plan,

        confidence=float(plan_output.get("confidence", 0.0) or 0.0),

        validation_errors_history=record.get("validation_errors_history") or [],
        context_errors=_extract_context_errors(record),

        semantic_evaluation=semantic_evaluation,
        difficulty=test_info.get("difficulty"),
        test_target=test_info.get("test_target"),
    )


# ==============================================================================
# UNIVERSI DI RIFERIMENTO
# ==============================================================================

def _supported_domain_tests(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    return [
        outcome
        for outcome in outcomes
        if not outcome.crashed and outcome.expected_domain != "unknown"
    ]


def _semantic_eligible(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    return [
        outcome
        for outcome in outcomes
        if not outcome.crashed and outcome.expected_domain != "unknown" and not outcome.plan_is_empty
    ]


# ==============================================================================
# METRICHE ANALITICHE
# ==============================================================================

def success_rate(outcomes: list[TestOutcome]) -> float:
    return _pct(sum(outcome.success for outcome in outcomes), len(outcomes))


def domain_accuracy(outcomes: list[TestOutcome]) -> float:
    return _pct(sum(outcome.domain_correct for outcome in outcomes), len(outcomes))


def valid_plan_rate(outcomes: list[TestOutcome]) -> float:
    relevant = _supported_domain_tests(outcomes)
    valid = sum(1 for outcome in relevant if not outcome.plan_is_empty)
    return _pct(valid, len(relevant))


def empty_plan_rate(outcomes: list[TestOutcome]) -> float:
    relevant = _supported_domain_tests(outcomes)
    empty = sum(1 for outcome in relevant if outcome.plan_is_empty)
    return _pct(empty, len(relevant))


def first_try_pass_rate(outcomes: list[TestOutcome]) -> float:
    relevant = _supported_domain_tests(outcomes)
    first_try = sum(
        1 for outcome in relevant
        if not outcome.validation_errors_history
        and not outcome.plan_is_empty
        and outcome.domain_correct
    )
    return _pct(first_try, len(relevant))


def final_failure_rate(outcomes: list[TestOutcome]) -> float:
    relevant = _supported_domain_tests(outcomes)
    failed = sum(1 for outcome in relevant if not outcome.success)
    return _pct(failed, len(relevant))


def self_correction_recovery_rate(outcomes: list[TestOutcome]) -> float:
    needed_correction = [
        outcome for outcome in _supported_domain_tests(outcomes)
        if outcome.validation_errors_history
    ]
    recovered = sum(
        1 for outcome in needed_correction
        if outcome.success and not outcome.plan_is_empty
    )
    return _pct(recovered, len(needed_correction))


def avg_confidence(outcomes: list[TestOutcome]) -> float:
    pool = [
        outcome for outcome in outcomes
        if outcome.success and not outcome.plan_is_empty
    ]
    values = [outcome.confidence for outcome in pool if outcome.confidence is not None]
    return round(mean(values), 3) if values else 0.0


def system_crash_rate(outcomes: list[TestOutcome]) -> float:
    return _pct(sum(outcome.crashed for outcome in outcomes), len(outcomes))


# ==============================================================================
# ERRORI VALIDAZIONE
# ==============================================================================

_ERROR_CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^il draft è vuoto"), "draft_vuoto_o_non_json"),
    (re.compile(r"^il campo 'title'"), "campo_title_mancante"),
    (re.compile(r"^il campo 'summary'"), "campo_summary_tipo_errato"),
    (re.compile(r"^il campo 'contingency_notes'"), "campo_contingency_notes_tipo_errato"),
    (re.compile(r"^il campo 'days'"), "days_mancante_o_vuoto"),
    (re.compile(r"^day_index non valido"), "day_index_non_valido"),
    (re.compile(r"^day_index \d+ duplicato"), "day_index_duplicato"),
    (re.compile(r"il campo 'label'"), "campo_label_tipo_errato"),
    (re.compile(r"campo 'date' malformato"), "formato_data_invalido"),
    (re.compile(r"nessuno slot presente o formato non valido"), "slots_mancanti_o_invalidi"),
    (re.compile(r"il campo 'task' è mancante"), "campo_task_mancante"),
    (re.compile(r"il campo 'category'"), "campo_category_tipo_errato"),
    (re.compile(r"il campo 'subtasks'"), "campo_subtasks_tipo_errato"),
    (re.compile(r"il campo 'notes'"), "campo_notes_tipo_errato"),
    (re.compile(r"duration_minutes non valido"), "duration_minutes_non_valido"),
    (re.compile(r"start_time malformato"), "formato_orario_invalido"),
    (re.compile(r"supera le 24 ore"), "durata_totale_giornaliera_eccessiva"),
    (re.compile(r"sovrapposizione tra"), "sovrapposizione_orari"),
    (re.compile(r"dominio 'routine' richiede esattamente i giorni 1-7"), "routine_giorni_incompleti"),
    (re.compile(r"day_index deve formare una sequenza contigua"), "day_index_non_contiguo"),
    (re.compile(r"^replan_identico"), "replan_non_effettuato"),
)


def _categorize(error_msg: str) -> str:
    for pattern, category in _ERROR_CATEGORY_PATTERNS:
        if pattern.search(error_msg):
            return category
    return "altro"


def validation_error_metrics(outcomes: list[TestOutcome]) -> dict[str, Any]:
    occurrences: Counter[str] = Counter()
    tests_affected: defaultdict[str, set[str]] = defaultdict(set)
    recovered: defaultdict[str, int] = defaultdict(int)

    for outcome in outcomes:
        categories_in_test: set[str] = set()
        for attempt_errors in outcome.validation_errors_history:
            for raw_error in attempt_errors:
                category = _categorize(raw_error)
                occurrences[category] += 1
                tests_affected[category].add(outcome.test_id)
                categories_in_test.add(category)

        if outcome.success:
            for category in categories_in_test:
                recovered[category] += 1

    ranked = sorted(
        occurrences.items(),
        key=lambda item: (len(tests_affected[item[0]]), item[1]),
        reverse=True,
    )

    return {
        "total_occurrences": sum(occurrences.values()),
        "categories": [
            {
                "category": category,
                "occurrences": count,
                "tests_affected": len(tests_affected[category]),
                "recovered_tests": recovered[category],
            }
            for category, count in ranked
        ],
    }


# ==============================================================================
# CONTESTO ESTERNO
# ==============================================================================

def external_failure_metrics(outcomes: list[TestOutcome]) -> dict[str, Any]:
    affected = [outcome for outcome in outcomes if outcome.context_errors]
    resilient = sum(
        1 for outcome in affected
        if not outcome.crashed and not outcome.plan_is_empty
    )
    return {
        "tests_with_context_errors": len(affected),
        "resilient_tests": resilient,
        "resilience_rate": _pct(resilient, len(affected)),
        "error_occurrences": sum(len(outcome.context_errors) for outcome in affected),
    }


# ==============================================================================
# SEMANTIC EVALUATION
# ==============================================================================

SEMANTIC_SCORE_FIELDS = {
    "groundedness": "groundedness_score",
    "semantic_adherence": "semantic_adherence_score",
    "human_feasibility": "human_feasibility_score",
    "granularity": "granularity_score",
    "replanning_consistency": "replanning_consistency_score",
}


def _semantic_scores(evaluation: dict[str, Any] | None) -> dict[str, float]:
    if not evaluation:
        return {}

    scores: dict[str, float] = {}
    for label, field in SEMANTIC_SCORE_FIELDS.items():
        value = evaluation.get(field)
        if value is None:
            continue
        try:
            scores[label] = float(value)
        except (TypeError, ValueError):
            continue
    return scores


def _semantic_overall(evaluation: dict[str, Any] | None) -> float | None:
    scores = _semantic_scores(evaluation)
    if not scores:
        return None
    return round(mean(scores.values()), 3)


def semantic_metrics(outcomes: list[TestOutcome]) -> dict[str, Any]:
    eligible = _semantic_eligible(outcomes)
    evaluated = [outcome for outcome in eligible if outcome.semantic_evaluation]

    dimension_values: defaultdict[str, list[float]] = defaultdict(list)
    overall_values: list[float] = []

    for outcome in evaluated:
        scores = _semantic_scores(outcome.semantic_evaluation)
        for dimension, value in scores.items():
            dimension_values[dimension].append(value)

        overall = _semantic_overall(outcome.semantic_evaluation)
        if overall is not None:
            overall_values.append(overall)

    dimensions = {}
    for dimension in SEMANTIC_SCORE_FIELDS:
        values = dimension_values[dimension]
        dimensions[dimension] = {
            "n": len(values),
            "mean": round(mean(values), 3) if values else None,
        }

    return {
        "eligible_tests": len(eligible),
        "evaluated_tests": len(evaluated),
        "coverage_rate": _pct(len(evaluated), len(eligible)),
        "overall_score": round(mean(overall_values), 3) if overall_values else None,
        "dimensions": dimensions,
    }


# ==============================================================================
# AGGREGAZIONE
# ==============================================================================

def _aggregate_outcomes(outcomes: list[TestOutcome]) -> dict[str, Any]:
    return {
        "n_test": len(outcomes),
        "success_rate": success_rate(outcomes),
        "domain_accuracy": domain_accuracy(outcomes),
        "valid_plan_rate": valid_plan_rate(outcomes),
        "empty_plan_rate": empty_plan_rate(outcomes),
        "zero_shot_rate": first_try_pass_rate(outcomes),
        "self_correction_recovery_rate": self_correction_recovery_rate(outcomes),
        "final_failure_rate": final_failure_rate(outcomes),
        "system_crash_rate": system_crash_rate(outcomes),
        "confidence_mean_successes": avg_confidence(outcomes),
        "validation_errors": validation_error_metrics(outcomes),
        "external_failures": external_failure_metrics(outcomes),
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


# ==============================================================================
# DETTAGLIO PER TEST
# ==============================================================================

def _test_detail(outcome: TestOutcome) -> dict[str, Any]:
    semantic_scores = _semantic_scores(outcome.semantic_evaluation)
    validation_attempts = len(outcome.validation_errors_history)

    return {
        "test_id": outcome.test_id,
        "difficulty": outcome.difficulty,
        "test_target": outcome.test_target,
        "model": outcome.model_name,
        "context_mode": outcome.context_mode,
        "expected_intent": outcome.expected_intent,
        "expected_domain": outcome.expected_domain,
        "actual_domain": outcome.actual_domain,
        "success": outcome.success,
        "domain_correct": outcome.domain_correct,
        "crashed": outcome.crashed,
        "plan_is_empty": outcome.plan_is_empty,
        "valid_plan": outcome.valid_plan,
        "confidence": outcome.confidence,
        "validation_attempts": validation_attempts,
        "context_error_count": len(outcome.context_errors),
        "semantic": {
            **semantic_scores,
            "overall": _semantic_overall(outcome.semantic_evaluation),
        },
    }


# ==============================================================================
# REPORT COMPLETO
# ==============================================================================

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
        "global": _aggregate_outcomes(outcomes),
        "by_model": _aggregate_groups(outcomes, "model_name"),
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


# ==============================================================================
# MARKDOWN REPORT
# ==============================================================================

def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _markdown_model_table(report: dict[str, Any]) -> str:
    rows = [
        "| Modello | Test | Successo | Domain Acc. | Zero-shot | Recovery | Semantic | Crash |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_name, metrics in report["by_model"].items():
        rows.append(
            "| " + " | ".join([
                model_name,
                _fmt(metrics["n_test"]),
                f"{metrics['success_rate']:.2f}%",
                f"{metrics['domain_accuracy']:.2f}%",
                f"{metrics['zero_shot_rate']:.2f}%",
                f"{metrics['self_correction_recovery_rate']:.2f}%",
                _fmt(metrics["semantic"]["overall_score"]),
                f"{metrics['system_crash_rate']:.2f}%",
            ]) + " |"
        )
    return "\n".join(rows)


def _markdown_semantic_table(report: dict[str, Any]) -> str:
    rows = [
        "| Modello | Groundedness | Adherence | Feasibility | Granularity | Replanning | Overall | Coverage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
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
            ]) + " |"
        )
    return "\n".join(rows)


def _markdown_simple_table(groups: dict[str, Any]) -> str:
    rows = [
        "| Gruppo | Test | Successo | Domain Accuracy | Semantic |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, metrics in groups.items():
        rows.append(
            "| " + " | ".join([
                key,
                str(metrics["n_test"]),
                f"{metrics['success_rate']:.2f}%",
                f"{metrics['domain_accuracy']:.2f}%",
                _fmt(metrics["semantic"]["overall_score"]),
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
        f"- Domain accuracy: **{global_metrics['domain_accuracy']:.2f}%**",
        f"- Valid plan rate: **{global_metrics['valid_plan_rate']:.2f}%**",
        f"- Zero-shot rate: **{global_metrics['zero_shot_rate']:.2f}%**",
        f"- Self-correction recovery: **{global_metrics['self_correction_recovery_rate']:.2f}%**",
        f"- Final failure rate: **{global_metrics['final_failure_rate']:.2f}%**",
        f"- Crash rate: **{global_metrics['system_crash_rate']:.2f}%**",
        f"- Confidence media (sui successi): **{global_metrics['confidence_mean_successes']:.3f}**",
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
            f"- Domain accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- Semantic coverage: **{metrics['semantic']['coverage_rate']:.2f}%**",
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
            f"- Domain accuracy: **{metrics['domain_accuracy']:.2f}%**",
            f"- Semantic score: **{_fmt(metrics['semantic']['overall_score'])} / 5**",
            f"- External resilience: **{metrics['external_failures']['resilience_rate']:.2f}%**",
            "",
        ])

    validation = global_metrics["validation_errors"]
    if validation["categories"]:
        lines.extend([
            "## 9. Validation errors",
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
        f"- Resilience rate: **{global_metrics['external_failures']['resilience_rate']:.2f}%**",
        f"- Occorrenze complessive: **{global_metrics['external_failures']['error_occurrences']}**",
        "",
        "## 11. Per-test details",
        "",
        "| Test | Difficoltà | Target | Modello | Context | Intent | Expected | Actual | Success | Semantic |",
        "|---|---|---|---|---|---|---|---|---|---:|",
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
                _fmt(test["semantic"]["overall"]),
            ]) + " |"
        )
    lines.append("")

    return "\n".join(lines)


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    dataset = _load_json(DATASET_PATH, [])
    raw_results = _load_json(RESULTS_PATH, {})
    semantic_results = _load_json(SEMANTIC_RESULTS_PATH, {})

    if not isinstance(raw_results, dict):
        raise ValueError("benchmark_results.json deve contenere un oggetto JSON.")

    if not isinstance(semantic_results, dict):
        semantic_results = {}

    report = build_report(
        records=list(raw_results.values()),
        semantic_evaluations=semantic_results,
        dataset=dataset if isinstance(dataset, list) else None,
    )

    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = generate_markdown(report)
    REPORT_MD_PATH.write_text(markdown, encoding="utf-8")

    print("=" * 70)
    print("BENCHMARK REPORT GENERATO (QUALITÀ & LOGICA)")
    print("=" * 70)
    print()
    print(f"JSON : {REPORT_JSON_PATH}")
    print(f"MD   : {REPORT_MD_PATH}")
    print()
    print(f"Test: {report['global']['n_test']}")
    print(f"Success rate: {report['global']['success_rate']:.2f}%")
    print(f"Domain accuracy: {report['global']['domain_accuracy']:.2f}%")
    print(f"Semantic score: {report['global']['semantic']['overall_score']}")
    print(f"Semantic coverage: {report['global']['semantic']['coverage_rate']:.2f}%")
    print()


if __name__ == "__main__":
    main()