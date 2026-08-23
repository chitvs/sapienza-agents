"""
Metriche pure calcolate a partire da liste di TestOutcome.

Ogni funzione riceve dati già in memoria (nessun accesso al filesystem)
e restituisce numeri o dizionari semplici: sono le funzioni da testare
direttamente con TestOutcome costruiti a mano, senza dataset o file di
benchmark reali su disco.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .model import TestOutcome


def _pct(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


# ==============================================================================
# UNIVERSI DI RIFERIMENTO
# ==============================================================================

def _supported_domain_tests(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    """
    Restituisce tutti i test relativi ai domini supportati.

    I crash NON vengono esclusi: un crash è una failure del sistema e deve
    rimanere nel denominatore delle metriche di performance.
    """
    return [
        outcome
        for outcome in outcomes
        if outcome.expected_domain != "unknown"
    ]


def _unknown_domain_tests(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    """
    Restituisce esclusivamente i test out-of-scope, ossia con expected_domain
    uguale a "unknown".
    """
    return [
        outcome
        for outcome in outcomes
        if outcome.expected_domain == "unknown"
    ]


def _semantic_eligible(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    """
    Test eleggibili per la valutazione semantica.

    Sono esclusi:
    - crash;
    - richieste out-of-scope;
    - piani vuoti.
    """
    return [
        outcome
        for outcome in outcomes
        if not outcome.crashed
        and outcome.expected_domain != "unknown"
        and not outcome.plan_is_empty
    ]


# ==============================================================================
# METRICHE ANALITICHE
# ==============================================================================

def success_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale complessiva di test superati.

    Include tutti i test, compresi gli out-of-scope e i crash.
    """
    return _pct(
        sum(outcome.success for outcome in outcomes),
        len(outcomes),
    )


def supported_success_rate(outcomes: list[TestOutcome]) -> float:
    """
    Success rate limitato ai domini supportati dal planner.

    È una metrica più specifica della success_rate globale quando il dataset
    contiene anche casi out-of-scope.
    """
    relevant = _supported_domain_tests(outcomes)

    return _pct(
        sum(outcome.success for outcome in relevant),
        len(relevant),
    )


def unknown_domain_accuracy(outcomes: list[TestOutcome]) -> float:
    """
    Accuratezza specifica nel riconoscimento delle richieste out-of-scope.

    Un test unknown è corretto quando il dominio prodotto è esattamente
    "unknown" e non c'è stato un crash.
    """
    relevant = _unknown_domain_tests(outcomes)

    correct = sum(
        1
        for outcome in relevant
        if not outcome.crashed
        and outcome.actual_domain == "unknown"
    )

    return _pct(correct, len(relevant))


def domain_accuracy(outcomes: list[TestOutcome]) -> float:
    """
    Accuratezza complessiva della classificazione del dominio.

    I crash restano nel denominatore e quindi vengono considerati errori.
    """
    return _pct(
        sum(outcome.domain_correct for outcome in outcomes),
        len(outcomes),
    )

def intent_accuracy(outcomes: list[TestOutcome]) -> float:
    """
    Accuratezza complessiva della classificazione dell'intento (es. new_plan vs replan).
    Viene calcolata solo sui test appartenenti ai domini supportati.
    I crash restano nel denominatore e vengono considerati errori.
    """
    relevant = _supported_domain_tests(outcomes)
    
    if not relevant:
        return 0.0

    correct = sum(
        1
        for outcome in relevant
        if not outcome.crashed
        and outcome.actual_intent == outcome.expected_intent
    )

    return _pct(correct, len(relevant))

def intent_confusion_matrix(outcomes: list[TestOutcome]) -> dict[str, dict[str, int]]:
    """
    Calcola la matrice di confusione degli intenti (expected vs actual) sui test supportati.
    Restituisce un dizionario nel formato: matrix[expected][actual] = count.
    """
    relevant = _supported_domain_tests(outcomes)
    matrix: defaultdict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    for outcome in relevant:
        actual = str(outcome.actual_intent) if outcome.actual_intent else "missing"
        matrix[outcome.expected_intent][actual] += 1
        
    return {k: dict(v) for k, v in matrix.items()}


def non_empty_plan_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test supportati in cui il planner ha prodotto un piano non vuoto
    senza crash. Indipendente dalla correttezza del dominio.
    """
    relevant = _supported_domain_tests(outcomes)
    valid = sum(1 for outcome in relevant if outcome.valid_plan)
    return _pct(valid, len(relevant))


def first_try_pass_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test supportati superati al primo tentativo.

    Un test è first-try quando:
    - non è crashato;
    - non ha generato errori di validazione;
    - ha prodotto un piano non vuoto;
    - il dominio è corretto;
    - il test complessivo è riuscito.
    """
    relevant = _supported_domain_tests(outcomes)

    first_try = sum(
        1
        for outcome in relevant
        if not outcome.crashed
        and not outcome.validation_errors_history
        and not outcome.plan_is_empty
        and outcome.domain_correct
        and outcome.success
    )

    return _pct(first_try, len(relevant))


def self_correction_recovery_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test che hanno richiesto almeno una correzione tramite
    validazione e sono infine riusciti.

    Il denominatore contiene esclusivamente i test per i quali è stata
    effettivamente necessaria una correzione.
    """
    needed_correction = [outcome for outcome in _supported_domain_tests(outcomes) if outcome.validation_errors_history]

    recovered = sum(1 for outcome in needed_correction if outcome.success and not outcome.plan_is_empty)

    return _pct(recovered, len(needed_correction))


def avg_confidence(outcomes: list[TestOutcome]) -> float:
    """
    Confidence media sui risultati riusciti e non vuoti.
    """
    pool = [outcome for outcome in outcomes if outcome.success and not outcome.plan_is_empty]

    values = [outcome.confidence for outcome in pool if math.isfinite(outcome.confidence)]

    return round(mean(values), 3) if values else 0.0


def avg_confidence_non_crashed(outcomes: list[TestOutcome]) -> float:
    """
    Confidence media su tutti i risultati valutabili senza crash e con piano
    non vuoto, indipendentemente dall'esito del test.
    """
    pool = [outcome for outcome in outcomes if not outcome.crashed and not outcome.plan_is_empty]

    values = [outcome.confidence for outcome in pool if math.isfinite(outcome.confidence)]

    return round(mean(values), 3) if values else 0.0


def system_crash_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test terminati con eccezione/crash.
    """
    return _pct(
        sum(outcome.crashed for outcome in outcomes),
        len(outcomes),
    )


def correction_failure_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test che hanno richiesto correzione (validation_errors_history > 0)
    ma che alla fine hanno comunque fallito.
    """
    needed_correction = [
        outcome 
        for outcome in _supported_domain_tests(outcomes) 
        if outcome.validation_errors_history
    ]
    failed_recovery = sum(1 for outcome in needed_correction if not outcome.success or outcome.plan_is_empty)
    return _pct(failed_recovery, len(needed_correction))


def validation_attempt_rate(outcomes: list[TestOutcome]) -> float:
    """
    Percentuale di test supportati che hanno innescato almeno un errore di validazione.
    Indica quanto spesso il modello 'inciampa' al primo colpo.
    """
    relevant = _supported_domain_tests(outcomes)
    needed = sum(1 for outcome in relevant if outcome.validation_errors_history)
    return _pct(needed, len(relevant))

def mean_attempts_per_corrected_test(outcomes: list[TestOutcome]) -> float:
    """
    Numero medio di tentativi di validazione calcolato *esclusivamente* sui test 
    che hanno richiesto correzione. Indica quanto è profondo il 'loop' di errore.
    """
    needed = [outcome for outcome in _supported_domain_tests(outcomes) if outcome.validation_errors_history]
    if not needed:
        return 0.0
    total = sum(len(outcome.validation_errors_history) for outcome in needed)
    return round(total / len(needed), 2)


def average_context_errors(outcomes: list[TestOutcome]) -> float:
    """Numero medio di errori di contesto esterno gestiti, per i test supportati."""
    relevant = _supported_domain_tests(outcomes)
    if not relevant:
        return 0.0
    total = sum(len(outcome.context_errors) for outcome in relevant)
    return round(total / len(relevant), 2)


def overconfidence_rate(outcomes: list[TestOutcome], threshold: float = 0.8) -> float:
    """
    Percentuale di test falliti in cui l'agente aveva assegnato una confidence 
    molto alta (>= threshold). Un valore alto indica che il modello "allucina"
    sicurezza quando in realtà sta sbagliando.
    """
    failed_tests = [outcome for outcome in outcomes if not outcome.success]

    if not failed_tests:
        return 0.0

    overconfident = sum(
        1 
        for outcome in failed_tests 
        if math.isfinite(outcome.confidence) and outcome.confidence >= threshold
    )

    return _pct(overconfident, len(failed_tests))

# ==============================================================================
# ERRORI VALIDAZIONE
# ==============================================================================
#
# Le seguenti regex fanno matching sui messaggi letterali generati da
# validators.py (validate_draft). Vanno aggiornate se cambia il testo
# di quei messaggi, altrimenti un nuovo tipo di errore finisce silenziosamente
# nella categoria "altro".

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
        "tests_with_validation_errors": len({
            outcome.test_id
            for outcome in outcomes
            if outcome.validation_errors_history
        }),
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
    """
    Analizza la resilienza del planner quando il context gathering incontra
    errori esterni.

    Un test è considerato resiliente se:
    - ha avuto almeno un errore di contesto;
    - non è crashato;
    - il test complessivo è comunque riuscito.
    """
    affected = [outcome for outcome in outcomes if outcome.context_errors]

    resilient = sum(1 for outcome in affected if not outcome.crashed and outcome.success)

    crashed = sum(1 for outcome in affected if outcome.crashed)

    failed = sum(1 for outcome in affected if not outcome.success)

    return {
        "tests_with_context_errors": len(affected),
        "resilient_tests": resilient,
        "failed_tests": failed,
        "crashed_tests": crashed,
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


def _coerce_semantic_score(raw_value: Any) -> float | None:
    """
    Converte un punteggio semantico grezzo in un float valido (1.0-5.0),
    o None se non convertibile, non finito o fuori range.

    Unica fonte di verità per la regola di validità: usata sia per
    filtrare i punteggi (_semantic_scores) sia per contare quelli non
    validi (semantic_metrics), per evitare che le due definizioni
    divergano nel tempo.
    """
    try:
        numeric_value = float(raw_value)
    except (TypeError, ValueError):
        return None

    return numeric_value if math.isfinite(numeric_value) and 1.0 <= numeric_value <= 5.0 else None


def _semantic_scores(evaluation: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(evaluation, dict):
        return {}

    scores: dict[str, float] = {}

    for label, field in SEMANTIC_SCORE_FIELDS.items():
        raw_value = evaluation.get(field)

        if raw_value is None:
            continue

        coerced = _coerce_semantic_score(raw_value)

        if coerced is not None:
            scores[label] = coerced

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

    invalid_score_values = 0
    partial_evaluations = 0

    for outcome in evaluated:
        raw_evaluation = outcome.semantic_evaluation or {}
        scores = _semantic_scores(raw_evaluation)

        # Conta come parziale una valutazione valida ma priva di almeno
        # una dimensione disponibile. Questo è normale nei new_plan,
        # dove la metrica di replanning può essere None.
        expected_dimensions = len(SEMANTIC_SCORE_FIELDS)
        if len(scores) < expected_dimensions:
            partial_evaluations += 1

        for field in SEMANTIC_SCORE_FIELDS.values():
            raw_value = raw_evaluation.get(field)
            if field in raw_evaluation and raw_value is not None and _coerce_semantic_score(raw_value) is None:
                invalid_score_values += 1

        for dimension, value in scores.items():
            dimension_values[dimension].append(value)

        overall = _semantic_overall(raw_evaluation)

        if overall is not None:
            overall_values.append(overall)

    dimensions: dict[str, dict[str, Any]] = {}

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
        "partial_evaluations": partial_evaluations,
        "invalid_score_values": invalid_score_values,
        "dimensions": dimensions,
    }