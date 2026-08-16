"""
Metriche di Affidabilita e Struttura per il benchmark del Planner Agent.
Opera sui risultati prodotti da run_benchmarks.py (benchmark_results.json):
un dict "test_id::model::context_mode" -> record di risultato per singolo test.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class TestOutcome:
    test_id: str
    model_name: str
    expected_domain: str
    actual_domain: str | None
    success: bool
    confidence: float
    plan_is_empty: bool
    crashed: bool
    validation_errors_history: list[list[str]]
    context_errors: list[str]


_CONTEXT_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(kg-agent|multiapi-agent): (timeout dopo|errore HTTP|errore di connessione|errore imprevisto)"),
    re.compile(r"^gather_context_react: "),
    re.compile(r"^tool sconosciuto: "),
)


def _extract_context_errors(record: dict[str, Any]) -> list[str]:
    """
    Isola gli errori di rete/contesto di un test. Fonte primaria: il campo
    strutturato QueryResponse.context_errors, propagato da pipeline._finalize
    e presente in plan_output. Fallback per risultati storici antecedenti
    all'aggiunta del campo: pattern-matching sui prefissi noti dentro
    contingency_notes.
    """
    plan_output = record.get("plan_output") or {}
    if "context_errors" in plan_output:
        return list(plan_output["context_errors"] or [])

    notes: list[str] = plan_output.get("contingency_notes") or []
    return [n for n in notes if any(p.match(n) for p in _CONTEXT_ERROR_PATTERNS)]


def normalize(record: dict[str, Any]) -> TestOutcome:
    """Converte un record grezzo di run_benchmarks.py in un TestOutcome."""
    plan_output = record.get("plan_output") or {}
    days = plan_output.get("days") or []
    return TestOutcome(
        test_id=record["test_id"],
        model_name=record["model_name"],
        expected_domain=record["expected_domain"],
        actual_domain=plan_output.get("domain"),
        success=bool(record.get("success")),
        confidence=float(plan_output.get("confidence", 0.0)),
        plan_is_empty=len(days) == 0,
        crashed=record.get("error") is not None,
        validation_errors_history=record.get("validation_errors_history") or [],
        context_errors=_extract_context_errors(record),
    )


def _pct(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


# --- 1. Tasso di successo globale ---

def success_rate(outcomes: list[TestOutcome]) -> float:
    """
    Per i domini attesi (study/travel/routine) richiede successo E piano
    non vuoto. Per le richieste fuori dominio ('unknown') il piano vuoto
    e' il comportamento corretto, quindi conta solo il rifiuto corretto.
    """
    def _ok(o: TestOutcome) -> bool:
        if o.expected_domain == "unknown":
            return o.success
        return o.success and not o.plan_is_empty

    return _pct(sum(1 for o in outcomes if _ok(o)), len(outcomes))


# --- 2/3. Zero-shot, fallimento e recupero da auto-correzione ---
#
# Le tre metriche condividono lo stesso universo di riferimento: i test in
# cui un piano era effettivamente atteso (esclude 'unknown', dove un piano
# vuoto e' il comportamento corretto) e in cui la pipeline non e' crashata
# (un crash e' un fallimento infrastrutturale, non del modello: vedi
# system_crash_rate). Su questo universo, zero-shot + fallimento coprono
# gia' il 100% (una bozza o è perfetta subito, o non lo è); tra quelle non
# perfette subito, self_correction_recovery_rate misura quante sono state
# comunque salvate dal loop di correzione.

def _in_scope_non_crashed(outcomes: list[TestOutcome]) -> list[TestOutcome]:
    return [o for o in outcomes if not o.crashed and o.expected_domain != "unknown"]


def first_try_pass_rate(outcomes: list[TestOutcome]) -> float:
    relevant = _in_scope_non_crashed(outcomes)
    ok = sum(1 for o in relevant if not o.validation_errors_history)
    return _pct(ok, len(relevant))


def failure_rate(outcomes: list[TestOutcome]) -> float:
    """Test in cui i tentativi di correzione sono stati esauriti senza un piano valido."""
    relevant = _in_scope_non_crashed(outcomes)
    failed = sum(1 for o in relevant if o.plan_is_empty)
    return _pct(failed, len(relevant))


def self_correction_recovery_rate(outcomes: list[TestOutcome]) -> float:
    """Tra i test NON perfetti al primo colpo, percentuale comunque recuperata entro il budget di retry."""
    needed_correction = [o for o in _in_scope_non_crashed(outcomes) if o.validation_errors_history]
    if not needed_correction:
        return 0.0
    recovered = sum(1 for o in needed_correction if not o.plan_is_empty)
    return _pct(recovered, len(needed_correction))


# --- 4. Confidence media ---

def avg_confidence(outcomes: list[TestOutcome], successful_only: bool = False) -> float:
    pool = [o for o in outcomes if not successful_only or (o.success and not o.plan_is_empty)]
    if not pool:
        return 0.0
    return round(sum(o.confidence for o in pool) / len(pool), 3)


# --- 5. Frequenza errori di validazione (categorizzati da validators.py) ---

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
)


def _categorize(error_msg: str) -> str:
    for pattern, category in _ERROR_CATEGORY_PATTERNS:
        if pattern.search(error_msg):
            return category
    return "altro"


def top_validation_errors(outcomes: list[TestOutcome], top_n: int = 5) -> list[dict[str, Any]]:
    occurrences: Counter[str] = Counter()
    tests_affected: defaultdict[str, set[str]] = defaultdict(set)

    for outcome in outcomes:
        for attempt_errors in outcome.validation_errors_history:
            for raw_error in attempt_errors:
                category = _categorize(raw_error)
                occurrences[category] += 1
                tests_affected[category].add(outcome.test_id)

    ranked = sorted(
        occurrences.items(),
        key=lambda item: (len(tests_affected[item[0]]), item[1]),
        reverse=True,
    )
    return [
        {"category": cat, "occurrences": count, "tests_affected": len(tests_affected[cat])}
        for cat, count in ranked[:top_n]
    ]


# --- 6. Accuratezza fuori dominio ---

def out_of_scope_accuracy(outcomes: list[TestOutcome]) -> float:
    oos = [o for o in outcomes if o.expected_domain == "unknown"]
    correct = sum(1 for o in oos if o.actual_domain == "unknown" and o.plan_is_empty)
    return _pct(correct, len(oos))


# --- 7. Resilienza ai fallimenti esterni ---

def external_failure_resilience_rate(outcomes: list[TestOutcome]) -> float:
    with_context_errors = [o for o in outcomes if o.context_errors]
    resilient = sum(1 for o in with_context_errors if not o.plan_is_empty and not o.crashed)
    return _pct(resilient, len(with_context_errors))


# --- extra: crash di sistema (distinto dai fallimenti "puliti") ---

def system_crash_rate(outcomes: list[TestOutcome]) -> float:
    return _pct(sum(1 for o in outcomes if o.crashed), len(outcomes))


def build_report(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Raggruppa i risultati grezzi per modello e calcola tutte le metriche."""
    by_model: defaultdict[str, list[TestOutcome]] = defaultdict(list)
    for record in records:
        outcome = normalize(record)
        by_model[outcome.model_name].append(outcome)

    report: dict[str, dict[str, Any]] = {}
    for model_name, outcomes in by_model.items():
        report[model_name] = {
            "n_test": len(outcomes),
            "tasso_successo_globale": success_rate(outcomes),
            "tasso_successo_zero_shot": first_try_pass_rate(outcomes),
            "tasso_recupero_auto_correzione": self_correction_recovery_rate(outcomes),
            "tasso_fallimento": failure_rate(outcomes),
            "tasso_crash_sistema": system_crash_rate(outcomes),
            "confidence_media": avg_confidence(outcomes),
            "confidence_media_sui_successi": avg_confidence(outcomes, successful_only=True),
            "top_errori_validazione": top_validation_errors(outcomes),
            "accuratezza_fuori_dominio": out_of_scope_accuracy(outcomes),
            "resilienza_fallimenti_esterni": external_failure_resilience_rate(outcomes),
        }
    return report


if __name__ == "__main__":
    import json
    from pathlib import Path

    results_path = Path(__file__).resolve().parent / "benchmark_results.json"
    raw_results: dict[str, Any] = json.loads(results_path.read_text(encoding="utf-8"))
    print(json.dumps(build_report(list(raw_results.values())), ensure_ascii=False, indent=2))