"""
Persistenza su disco: percorsi dei file di benchmark e lettura/scrittura
dei relativi JSON/Markdown. Unico modulo del package che tocca il
filesystem: model.py, analytics.py e aggregate.py lavorano solo su
dati già in memoria.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BENCHMARK_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BENCHMARK_DIR / "data"

DATASET_PATH = DATA_DIR / "benchmark_dataset.json"
RESULTS_PATH = DATA_DIR / "benchmark_results.json"
SEMANTIC_RESULTS_PATH = DATA_DIR / "semantic_eval_results.json"
REPORT_JSON_PATH = DATA_DIR / "benchmark_report.json"
REPORT_MD_PATH = DATA_DIR / "benchmark_report.md"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return default

    return json.loads(content)


def write_report(report: dict[str, Any], markdown: str) -> None:
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(markdown, encoding="utf-8")