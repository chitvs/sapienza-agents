"""
Orchestrazione della generazione del report: carica gli input da disco
(io.py), costruisce il report (aggregate.py), lo renderizza in Markdown
(report_md.py) e scrive entrambi gli output. Sostituisce il vecchio
main() di metrics.py.
"""

from __future__ import annotations

from . import io
from .aggregate import build_report
from .report_md import generate_markdown


def main() -> None:
    dataset = io.load_json(io.DATASET_PATH, [])
    raw_results = io.load_json(io.RESULTS_PATH, {})
    semantic_results = io.load_json(io.SEMANTIC_RESULTS_PATH, {})

    if not isinstance(raw_results, dict):
        raise ValueError("benchmark_results.json deve contenere un oggetto JSON.")

    if not isinstance(semantic_results, dict):
        semantic_results = {}

    report = build_report(
        records=list(raw_results.values()),
        semantic_evaluations=semantic_results,
        dataset=dataset if isinstance(dataset, list) else None,
    )

    markdown = generate_markdown(report)
    io.write_report(report, markdown)

    print("=" * 70)
    print("BENCHMARK REPORT GENERATO (QUALITÀ & LOGICA)")
    print("=" * 70)
    print()
    print(f"JSON : {io.REPORT_JSON_PATH}")
    print(f"MD   : {io.REPORT_MD_PATH}")
    print()
    print(f"Test: {report['global']['n_test']}")
    print(f"Supported-domain success rate: {report['global']['supported_success_rate']:.2f}%")
    print(f"Domain accuracy: {report['global']['domain_accuracy']:.2f}%")
    print(f"Intent accuracy: {report['global']['intent_accuracy']:.2f}%")
    print(f"Non-empty plan rate: {report['global']['non_empty_plan_rate']:.2f}%")
    print(f"Crash rate: {report['global']['system_crash_rate']:.2f}%")
    print(f"Semantic score: {report['global']['semantic']['overall_score']}")
    print(f"Semantic coverage: {report['global']['semantic']['coverage_rate']:.2f}%")
    print()
    print()