"""
Misura se la rigenerazione ReAct produce davvero una query diversa, e a quale temperatura.

Per ogni domanda arriva fino alla prima esecuzione; se restituisce 0 righe, rigenera la
query con il prompt di feedback a piu' configurazioni di campionamento e riporta quante
volte l'output e' identico all'originale e quante volte recupera righe.
"""

import argparse
import json
import sys
import time
from pathlib import Path

KG = Path(__file__).resolve().parents[2]
REPO = KG.parents[1]
EVALUATIONS_DIR = KG / "data" / "evaluations"
sys.path.insert(0, str(KG / "src"))
sys.path.insert(0, str(KG / "benchmarks"))
sys.path.insert(0, str(REPO))

from evaluate_qald import (  # noqa: E402
    BENCHMARKS,
    english_question,
    load_dataset,
    question_kind,
    stratified_sample,
)

CONFIGS = [("t0.0", 0.0, None), ("t1.0_p0.9", 1.0, 0.9)]

BENCHMARK = BENCHMARKS["qald10"]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--samples-per-config", type=int, default=3)
    parser.add_argument("--out", default=str(EVALUATIONS_DIR / "retry_trials.json"))
    args = parser.parse_args()

    from cache.null_cache import NullCache
    from pipeline import KGPipeline

    dataset = [e for e in load_dataset(BENCHMARK) if english_question(e)]
    entries = stratified_sample(dataset, args.sample, args.seed, BENCHMARK.predicates)
    pipeline = KGPipeline(target_kg=BENCHMARK.target_kg, cache=NullCache())
    records: list[dict] = []

    for i, entry in enumerate(entries, start=1):
        question = english_question(entry)
        kind = question_kind(entry["query"]["sparql"], BENCHMARK.predicates)
        started = time.time()
        try:
            entities = pipeline.linker.link(question)
            seeds = [e.id for e in entities if e.id]
            relation_query = pipeline._relation_query(question, entities)
            pruned = pipeline.pruner.prune(seed_entity_ids=seeds, question=relation_query or question)
            schema_context = pruned.context_text or "\n".join(
                f"entità: {e.label} (id:{e.id})" for e in entities
            )
            query = pipeline.translator.translate(question=question, schema_context=schema_context)
            rows, query, _ = pipeline._execute_with_correction(query, question, schema_context)
        except Exception as err:
            print(f"[{i}/{len(entries)}] {kind:6} SKIP (eccezione) {type(err).__name__}: {str(err)[:60]}", flush=True)
            continue

        if rows:
            print(f"[{i}/{len(entries)}] {kind:6} ok al primo colpo ({len(rows)} righe)", flush=True)
            continue

        # il rilassamento dei filtri di classe precede l'LLM anche nella pipeline reale
        relaxed = pipeline.translator.relax_constraints(query)
        relaxed_ok = False
        if relaxed:
            try:
                relaxed_rows, _, _ = pipeline._execute_with_correction(relaxed, question, schema_context)
                relaxed_ok = bool(relaxed_rows)
            except Exception:
                relaxed_ok = False

        feedback = pipeline.translator.generate_feedback_prompt(query=query, schema_context=schema_context)
        trials: list[dict] = []
        for name, temperature, top_p in CONFIGS:
            for k in range(args.samples_per_config):
                try:
                    retry = pipeline.translator.translate(
                        question=question, schema_context=feedback, temperature=temperature, top_p=top_p
                    )
                except Exception as err:
                    trials.append({"config": name, "k": k, "identical": None,
                                   "outcome": f"llm:{type(err).__name__}", "rows": 0, "query": ""})
                    continue
                try:
                    retry_rows, _, _ = pipeline._execute_with_correction(retry, question, schema_context)
                    outcome = "rows" if retry_rows else "empty"
                except Exception as err:
                    retry_rows, outcome = [], f"error:{type(err).__name__}"
                trials.append({
                    "config": name, "k": k, "identical": retry.strip() == query.strip(),
                    "outcome": outcome, "rows": len(retry_rows or []), "query": retry,
                })

        record = {
            "id": entry.get("id"), "kind": kind, "question": question,
            "initial_query": query, "relax_recovers": relaxed_ok,
            "trials": trials, "seconds": round(time.time() - started, 1),
        }
        records.append(record)
        summary = " ".join(
            f"{t['config']}#{t['k']}={'=' if t['identical'] else '~'}{t['outcome']}" for t in trials
        )
        print(f"[{i}/{len(entries)}] {kind:6} VUOTA relax={relaxed_ok} | {summary} | {question[:50]}", flush=True)
        Path(args.out).write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\ncasi di rigenerazione raccolti: {len(records)}")
    for name, _, _ in CONFIGS:
        trials = [t for r in records for t in r["trials"] if t["config"] == name]
        if not trials:
            continue
        identical = sum(1 for t in trials if t["identical"])
        recoveries = sum(1 for t in trials if t["outcome"] == "rows")
        print(f"  {name:10} identiche {identical}/{len(trials)}   con righe {recoveries}/{len(trials)}")
    print(f"dettaglio in {args.out}")

if __name__ == "__main__":
    main()
