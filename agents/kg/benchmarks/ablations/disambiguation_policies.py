"""Confronta le politiche di ranking sui segnali raccolti, separando i casi facili dagli ambigui."""

import json
import math
import sys
from pathlib import Path

EVALUATIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluations"

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else str(EVALUATIONS_DIR / "disambiguation_signals.json"))

def rescale(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    return [0.5] * len(values) if high == low else [(v - low) / (high - low) for v in values]

POLICIES = {
    "primo (attuale)": lambda c, p, r: r,
    "solo contesto": lambda c, p, r: c,
    "solo notorieta": lambda c, p, r: p,
    "contesto+notorieta": lambda c, p, r: [(a + b) / 2 for a, b in zip(c, p)],
    "notorieta+rank": lambda c, p, r: [(a + b) / 2 for a, b in zip(p, r)],
    "contesto+rank": lambda c, p, r: [(a + b) / 2 for a, b in zip(c, r)],
    "tutti e tre": lambda c, p, r: [(a + b + d) / 3 for a, b, d in zip(c, p, r)],
}

def main() -> None:
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"menzioni con il QID corretto fra i candidati: {len(cases)}")

    easy = [k for k in cases if k["correct"][0]]
    ambiguous = [k for k in cases if not k["correct"][0]]
    print(f"  di cui il primo candidato è già corretto: {len(easy)}")
    print(f"  di cui il primo candidato è sbagliato:    {len(ambiguous)}\n")

    print(f"{'politica':26} {'totale':>14} {'recuperati':>12} {'mantenuti':>12} {'netto':>7}")
    for name, policy in POLICIES.items():
        recovered = kept = 0
        for group, bucket in ((ambiguous, "rec"), (easy, "keep")):
            for k in group:
                n = len(k["ids"])
                scores = policy(
                    rescale(k["similarities"]),
                    rescale([math.log1p(s) for s in k["sitelinks"]]),
                    rescale([1.0 / math.log2(i + 2) for i in range(n)]),
                )
                hit = k["correct"][max(range(n), key=lambda i: scores[i])]
                if bucket == "rec":
                    recovered += hit
                else:
                    kept += hit
        total = recovered + kept
        # il netto sottrae i casi facili persi: una politica che ne recupera dieci e ne
        # rompe dodici peggiora il sistema, pur alzando il conteggio degli ambigui risolti
        net = recovered - (len(easy) - kept)
        print(f"{name:26} {total:4}/{len(cases):<4} ({total / len(cases):.3f}) "
              f"{recovered:4}/{len(ambiguous):<4} {kept:5}/{len(easy):<4} {net:+7}")

if __name__ == "__main__":
    main()
