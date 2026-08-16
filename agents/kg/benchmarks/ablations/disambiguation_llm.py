"""
Misura se la disambiguazione via LLM batte il ranking senza LLM, sugli stessi casi.
"""

import json
import math
import sys
from pathlib import Path

KG = Path(__file__).resolve().parents[2]
REPO = KG.parents[1]
EVALUATIONS_DIR = KG / "data" / "evaluations"
sys.path.insert(0, str(KG / "src"))
sys.path.insert(0, str(REPO))

from connectors.base_connector import EntityCandidate
from connectors.wikidata_connector import WikidataConnector
from linkers.entity_linker import EntityLinker

DATA = Path(str(EVALUATIONS_DIR / "disambiguation_signals.json"))

def rescale(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    return [0.5] * len(values) if high == low else [(v - low) / (high - low) for v in values]

def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]
    linker = EntityLinker(connector=WikidataConnector())

    llm_hits = llm_inconclusive = ranking_hits = first_hits = 0
    for n, k in enumerate(cases, start=1):
        cands = [
            EntityCandidate(id=i, label=lab, description=desc)
            for i, lab, desc in zip(k["ids"], k["labels"], k["descriptions"])
        ]
        scores = [
            (a + b + c) / 3 for a, b, c in zip(
                rescale(k["similarities"]),
                rescale([math.log1p(s) for s in k["sitelinks"]]),
                rescale([1.0 / math.log2(i + 2) for i in range(len(cands))]),
            )
        ]
        ranking_hits += k["correct"][max(range(len(cands)), key=lambda i: scores[i])]
        first_hits += k["correct"][0]

        try:
            system_prompt = linker.llm_client.load_prompt(
                "disambiguate_entity.txt",
                question=k["question"],
                mention=k["mention"],
                candidates_json=json.dumps(
                    [{"id": c.id, "label": c.label, "description": c.description} for c in cands],
                    indent=2, ensure_ascii=False,
                ),
            )
            raw = linker.llm_client.chat(
                system_prompt=system_prompt, user_content=k["question"], temperature=0.0
            )
            chosen = linker._select_from_output(raw, {c.id: c for c in cands})
        except Exception:
            chosen = None

        if chosen is None:
            llm_inconclusive += 1
        else:
            llm_hits += k["correct"][k["ids"].index(chosen.id)]

        if n % 20 == 0:
            print(f"  ...{n}/{len(cases)}", flush=True)

    print(f"\nmenzioni valutate: {len(cases)}")
    print(f"  primo candidato       {first_hits:4}/{len(cases)}  ({first_hits / len(cases):.3f})")
    print(f"  ranking senza llm     {ranking_hits:4}/{len(cases)}  ({ranking_hits / len(cases):.3f})")
    # due denominatori diversi, perché rispondono a due domande diverse: quanto è
    # accurato l'LLM quando decide, e quanto rende sull'intero carico di menzioni
    conclusive = len(cases) - llm_inconclusive
    if conclusive:
        print(f"  llm (solo conclusive) {llm_hits:4}/{conclusive}  ({llm_hits / conclusive:.3f})")
    print(f"  llm (su tutti i casi) {llm_hits:4}/{len(cases)}  ({llm_hits / len(cases):.3f})")
    print(f"  llm inconcludenti     {llm_inconclusive:4}/{len(cases)}")

if __name__ == "__main__":
    main()
