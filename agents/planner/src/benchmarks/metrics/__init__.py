"""
Package di metriche e reporting per il benchmark del Planner Agent.

Split in moduli per responsabilità:
    model.py      - TestOutcome + normalize() (pura)
    analytics.py  - tutte le metriche calcolate su list[TestOutcome] (pura)
    aggregate.py  - build_report(), i breakdown per gruppo (pura)
    report_md.py  - rendering Markdown del report (pura)
    io.py         - percorsi e lettura/scrittura su disco (unico I/O)
    run.py        - orchestrazione (main())
"""

from .aggregate import build_report
from .io import (
    DATASET_PATH,
    REPORT_JSON_PATH,
    REPORT_MD_PATH,
    RESULTS_PATH,
    SEMANTIC_RESULTS_PATH,
    load_json,
)
from .model import TestOutcome, normalize
from .report_md import generate_markdown
from .run import main

__all__ = [
    "TestOutcome",
    "normalize",
    "build_report",
    "generate_markdown",
    "main",
    "DATASET_PATH",
    "RESULTS_PATH",
    "SEMANTIC_RESULTS_PATH",
    "REPORT_JSON_PATH",
    "REPORT_MD_PATH",
    "load_json",
]