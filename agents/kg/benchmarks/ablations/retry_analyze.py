"""
Riassume i risultati di retry_collect.py.
"""

import json
import sys
from pathlib import Path

EVALUATIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluations"

path = Path(sys.argv[1] if len(sys.argv) > 1 else str(EVALUATIONS_DIR / "retry_trials.json"))
records = json.loads(path.read_text(encoding="utf-8"))

print(f"casi con 0 righe al primo tentativo: {len(records)}")
print(f"  di cui recuperati dal relax dei filtri di classe: {sum(1 for r in records if r['relax_recovers'])}")

configs = sorted({t["config"] for r in records for t in r["trials"]})
print(f"\n{'config':12} {'identiche':>12} {'con righe':>12} {'errori':>8} {'>=1 recupero':>14}")
for name in configs:
    trials = [t for r in records for t in r["trials"] if t["config"] == name]
    # i tentativi in cui l'LLM è fallito non hanno prodotto una query
    comparable = [t for t in trials if t["identical"] is not None]
    identical = sum(1 for t in comparable if t["identical"])
    with_rows = sum(1 for t in trials if t["outcome"] == "rows")
    errors = sum(1 for t in trials if t["outcome"].startswith(("error", "llm")))
    at_least_one = sum(
        1 for r in records
        if any(t["config"] == name and t["outcome"] == "rows" for t in r["trials"])
    )
    print(f"{name:12} {identical:>6}/{len(comparable):<5} {with_rows:>6}/{len(trials):<5} {errors:>8} {at_least_one:>8}/{len(records)}")

print("\ncasi in cui almeno una configurazione ha recuperato righe:")
for r in records:
    winners = sorted({t["config"] for t in r["trials"] if t["outcome"] == "rows"})
    if winners:
        print(f"  [{r['kind']:6}] {r['question'][:60]:60} -> {', '.join(winners)}")
