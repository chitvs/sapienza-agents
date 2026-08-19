"""
Baseline closed-book: le stesse domande poste al modello senza knowledge graph.

Uso:
    python benchmarks/baselines/closed_book.py --gold executed
    python benchmarks/baselines/closed_book.py --benchmark qald9plus --gold executed
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

KG = Path(__file__).resolve().parents[2]
REPO = KG.parents[1]
sys.path.insert(0, str(KG / "src"))
sys.path.insert(0, str(KG / "benchmarks"))
sys.path.insert(0, str(REPO))

from configs.settings import settings
from evaluate_qald import (
    BENCHMARKS,
    REPORT_DIR,
    english_question,
    executed_gold,
    gold_answers,
    has_usable_gold,
    load_dataset,
    normalize,
    question_kind,
    score,
    stratified_sample,
    write_json,
)
from models.llm import build_llm_client
from providers import build_provider
from shared.ollama_client import OllamaClient

# il tipo di risposta atteso non viene dichiarato al modello: dedurlo dalla domanda fa
# parte del compito, esattamente come la pipeline deve scegliere da sola fra ASK, COUNT
# e SELECT. Dirglielo significherebbe passargli un'informazione ricavata dalla query gold.
SYSTEM_PROMPT = """You answer questions using only your own knowledge. You have no access to any database or search engine.

Reply with a single JSON object and nothing else: {"answer": <value>}

Infer the shape of <value> from the question itself:
- true or false for a yes/no question
- a number for a "how many" question
- a list of strings otherwise, one entry per distinct answer, each the most common English name

If you do not know the answer, reply {"answer": []}. Never invent a plausible name."""

def load_json(text: str) -> object:
    """Decodifica il JSON, restituendo None invece di sollevare se il testo non lo è."""
    try:
        return json.loads(text)
    except ValueError:
        return None

def parse_answer(raw: str) -> set[str] | bool | None:
    """Interpreta la risposta del modello; None se non ha rispettato il formato richiesto."""
    text = OllamaClient.clean_code_block(raw)
    payload = load_json(text)
    if payload is None:
        # i modelli piccoli premettono spesso una frase di cortesia all'oggetto JSON
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        payload = load_json(match.group(0)) if match else None
    if not isinstance(payload, dict) or "answer" not in payload:
        return None

    value = payload["answer"]
    # il booleano va riconosciuto prima del numero: in Python True è anche un int
    if isinstance(value, bool):
        return value
    if value is None:
        return set()
    if isinstance(value, (int, float, str)):
        return {normalize(value)} if str(value).strip() else set()
    if isinstance(value, list):
        return {normalize(v) for v in value if str(v).strip()}
    return None

def main() -> None:
    parser = argparse.ArgumentParser(description="baseline senza knowledge graph sui benchmark QALD")
    parser.add_argument("--benchmark", choices=tuple(BENCHMARKS), default="qald10")
    parser.add_argument("--sample", type=int, default=0, help="numero di domande (0 = tutte)")
    parser.add_argument("--seed", type=int, default=0, help="seme del campionamento, per ripetere lo stesso sottoinsieme")
    parser.add_argument(
        "--gold",
        choices=("recorded", "executed"),
        default="recorded",
        help="deve coincidere con quello usato per la pipeline, altrimenti i due numeri non sono confrontabili",
    )
    # il modello di traduzione è specializzato sul codice: come baseline di conoscenza
    # sarebbe un avversario di comodo, quindi si interroga quello istruito
    parser.add_argument("--model", default=settings.ollama_linking_model, help="modello da interrogare")
    args = parser.parse_args()

    benchmark = BENCHMARKS[args.benchmark]
    entries = [e for e in load_dataset(benchmark) if english_question(e)]
    if args.sample:
        entries = stratified_sample(entries, args.sample, args.seed, benchmark.predicates)

    # il grafo interviene solo per costruire il riferimento e per risolvere le etichette
    # del gold in fase di punteggio: la baseline non lo interroga mai per rispondere
    provider = build_provider(benchmark.target_kg)
    executed = args.gold == "executed"
    regenerated_gold = executed_gold(entries, benchmark, provider) if executed else {}

    golds: dict[str, object] = {}
    for entry in entries:
        key = str(entry.get("id"))
        if executed:
            value = regenerated_gold.get(key)
            golds[key] = set(value) if isinstance(value, list) else value
        else:
            golds[key] = gold_answers(entry)

    # si scartano le stesse domande che scarta la pipeline, altrimenti i due macro-F1
    # sarebbero calcolati su popolazioni diverse e il confronto perderebbe senso
    usable = [e for e in entries if has_usable_gold(golds[str(e.get("id"))])]
    if len(usable) != len(entries):
        print(f"escluse {len(entries) - len(usable)} domande senza gold utilizzabile")
        entries = usable

    print(f"{benchmark.label} | baseline senza grafo, modello {args.model}")
    print(f"domande da valutare: {len(entries)}")

    client = build_llm_client(args.model)
    results: list[dict] = []
    started = time.time()
    report_path = REPORT_DIR / f"closedbook_{args.benchmark}_{time.strftime('%Y%m%d_%H%M%S')}.json"

    def save_report() -> None:
        """Salva su disco ciò che è stato valutato finora."""
        if not results:
            return
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(report_path, {
            "benchmark": benchmark.label, "target_kg": benchmark.target_kg, "gold": args.gold,
            "baseline": "closed-book", "model": args.model,
            "evaluated": len(results), "selected": len(entries),
            "macro_f1": sum(r["f1"] for r in results) / len(results), "results": results,
        })

    def summarize() -> None:
        """Stampa il riepilogo e salva il report di ciò che è stato valutato finora."""
        if not results:
            print("nessuna domanda valutata: campione vuoto o nessun gold utilizzabile")
            return
        macro_f1 = sum(r["f1"] for r in results) / len(results)
        print(f"\nmacro-F1: {macro_f1:.3f}   su {len(results)} domande, in {(time.time() - started) / 60:.1f} minuti")
        print("per tipo di domanda:")
        for kind in sorted({r["kind"] for r in results}):
            group = [r for r in results if r["kind"] == kind]
            print(f"  {kind:6} F1={sum(r['f1'] for r in group) / len(group):.3f}  ({len(group)} domande)")
        malformed = sum(1 for r in results if r["error"])
        # il confronto con la lista vuota è indispensabile: un'astensione è [], ma anche
        # il booleano False è falso in Python e finirebbe contato come astensione
        abstained = sum(1 for r in results if not r["error"] and r["ours"] == [])
        print(f"formato non rispettato: {malformed}   dichiara di non sapere: {abstained}")

        save_report()
        print(f"dettaglio in {report_path}")

    try:
        for i, entry in enumerate(entries, start=1):
            question = english_question(entry)
            kind = question_kind(entry["query"]["sparql"], benchmark.predicates)
            gold = golds[str(entry.get("id"))]
            question_started = time.time()
            try:
                raw = client.chat(system_prompt=SYSTEM_PROMPT, user_content=question, temperature=0.0)
                ours = parse_answer(raw)
                error = "" if ours is not None else "risposta non conforme al formato richiesto"
            except Exception as err:
                raw, ours, error = "", None, f"{type(err).__name__}: {err}"

            if ours is None:
                ours = set()
            precision, recall, f1 = (0.0, 0.0, 0.0) if error else score(gold, ours, provider.connector)

            results.append({
                "id": entry.get("id"), "kind": kind, "question": question, "f1": f1,
                "precision": precision, "recall": recall, "error": error,
                "gold": sorted(gold) if isinstance(gold, set) else gold,
                "ours": sorted(ours) if isinstance(ours, set) else ours,
                "raw": raw, "seconds": round(time.time() - question_started, 1),
            })
            print(f"[{i}/{len(entries)}] {kind:6} F1={f1:.2f}  {question[:64]}" + (f"  !{error[:40]}" if error else ""))

            if i % 25 == 0:
                save_report()
    finally:
        summarize()

if __name__ == "__main__":
    main()
