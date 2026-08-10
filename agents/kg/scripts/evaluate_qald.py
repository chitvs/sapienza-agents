"""
Valuta la pipeline su QALD-10 con la macro-F1.

Uso:
    python scripts/evaluate_qald.py --sample 30      # campione stratificato per tipo
    python scripts/evaluate_qald.py                  # tutte le domande
    python scripts/evaluate_qald.py --dry-run        # solo composizione del dataset
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

QALD_URL = "https://raw.githubusercontent.com/KGQA/QALD-10/main/data/qald_10/qald_10.json"
DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "qald_10.json"
REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "evaluations"

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def load_dataset() -> list[dict]:
    """Carica QALD-10, scaricandolo al primo utilizzo."""
    if not DATASET_PATH.exists():
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"scarico QALD-10 da {QALD_URL} ...")
        response = requests.get(QALD_URL, timeout=120)
        response.raise_for_status()
        DATASET_PATH.write_bytes(response.content)
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))["questions"]

def question_kind(sparql: str) -> str:
    """Classifica la domanda dalla query gold, per stratificare il campione."""
    upper = sparql.upper()
    if re.search(r"\bASK\b", upper):
        return "ask"
    if re.search(r"\bCOUNT\s*\(", upper):
        return "count"
    # il numero di triple approssima il numero di hop: una sola tripla è una domanda diretta
    body = re.search(r"WHERE\s*\{(.*)\}", sparql, flags=re.IGNORECASE | re.DOTALL)
    triples = len(re.findall(r"\bwdt:P\d+|\bp:P\d+", body.group(1) if body else sparql))
    return "single" if triples <= 1 else "multi"

def english_question(entry: dict) -> str | None:
    """Estrae la formulazione inglese, l'unica lingua che l'agente kg accetta."""
    for item in entry.get("question", []):
        if item.get("language") == "en":
            return item.get("string")
    return None

def normalize(value: Any) -> str:
    """Riduce un valore alla forma su cui ha senso confrontare gold e risposta."""
    text = str(value).strip()
    # il gold porta il timestamp completo, noi accorciamo alla data: si confronta la data
    match = re.match(r"^([+-]?\d{4,}-\d{2}-\d{2})T", text)
    if match:
        text = match.group(1)
    text = text.lstrip("+")
    # i numeri vanno confrontati per valore: "4" e "4.0" sono la stessa risposta
    try:
        number = float(text)
        return str(int(number)) if number == int(number) else str(number)
    except ValueError:
        return text.lower()

def gold_answers(entry: dict) -> set[str] | bool:
    """Estrae le risposte di riferimento; per le ASK restituisce il booleano."""
    answers = entry.get("answers") or [{}]
    block = answers[0]
    if "boolean" in block:
        return bool(block["boolean"])
    values: set[str] = set()
    for binding in block.get("results", {}).get("bindings", []):
        for cell in binding.values():
            if cell.get("value"):
                values.add(normalize(cell["value"]))
    return values

def system_answers(rows: list[dict]) -> set[str] | bool:
    """Estrae le risposte prodotte da noi, preferendo l'URI all'etichetta."""
    if len(rows) == 1 and "boolean" in rows[0]:
        return str(rows[0]["boolean"]).lower() in ("true", "1")

    values: set[str] = set()
    for row in rows:
        sources = row.get("_sources") or {}
        for key, value in row.items():
            if key.startswith("_"):
                continue
            # l'URI è l'identificatore stabile: le etichette cambiano fra lingue e revisioni
            values.add(normalize(sources.get(key, value)))
    return values

_QID = re.compile(r"/(Q\d+)$", re.IGNORECASE)

def alias_sets(values: set[str], connector: Any = None) -> list[set[str]]:
    """Rappresenta ogni risposta con le sue forme equivalenti, URI ed etichetta: le query gold
    proiettano l'entità e le nostre ?xLabel, e senza questo ogni risposta giusta sarebbe un errore."""
    qids = {m.group(1).upper() for v in values if (m := _QID.search(v))}
    labels: dict[str, str] = {}
    if qids and connector is not None:
        try:
            for qid, data in connector.get_entities(sorted(qids)).items():
                if data and data.label:
                    labels[qid.upper()] = normalize(data.label)
        except Exception as err:
            logger.warning("risoluzione etichette del gold fallita: %s", err)

    items: list[set[str]] = []
    for value in values:
        forms = {value}
        match = _QID.search(value)
        if match and match.group(1).upper() in labels:
            forms.add(labels[match.group(1).upper()])
        items.append(forms)
    return items

def score_items(gold_items: list[set[str]], our_items: list[set[str]]) -> tuple[float, float, float]:
    """F1 confrontando insiemi di forme equivalenti: due risposte coincidono se condividono una forma."""
    matched_gold = 0
    matched_ours: set[int] = set()
    for gold_forms in gold_items:
        for i, our_forms in enumerate(our_items):
            if i not in matched_ours and gold_forms & our_forms:
                matched_gold += 1
                matched_ours.add(i)
                break
    precision = len(matched_ours) / len(our_items)
    recall = matched_gold / len(gold_items)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1

def score(gold: set[str] | bool, ours: set[str] | bool, connector: Any = None) -> tuple[float, float, float]:
    """Precisione, richiamo e F1 di una singola domanda, con le convenzioni QALD."""
    if isinstance(gold, bool) or isinstance(ours, bool):
        correct = float(gold == ours)
        return correct, correct, correct
    if not gold and not ours:
        # nessuna risposta attesa e nessuna prodotta: la domanda è risolta correttamente
        return 1.0, 1.0, 1.0
    if not gold or not ours:
        return 0.0, 0.0, 0.0

    return score_items(alias_sets(gold, connector), alias_sets(ours, connector))

def executed_gold(entries: list[dict]) -> dict[str, Any]:
    """Rigenera le risposte di riferimento eseguendo le query gold, e le memorizza su disco."""
    # le risposte registrate in QALD-10 risalgono alla costruzione del benchmark e Wikidata è
    # cambiata: sui conteggi il disallineamento è sistematico. Confrontarsi con la query gold
    # eseguita oggi misura la qualità della nostra query invece dell'età del dataset.
    cache_path = DATASET_PATH.with_name("qald_10_executed.json")
    cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    from connectors.wikidata_connector import WikidataConnector
    from executors.sparql_executor import SPARQLExecutor

    executor, connector = SPARQLExecutor(timeout=30), WikidataConnector()
    for entry in entries:
        key = str(entry.get("id"))
        if key in cache:
            continue
        try:
            answers = system_answers(connector.ground_results(executor.execute(entry["query"]["sparql"])))
            cache[key] = sorted(answers) if isinstance(answers, set) else answers
        except Exception as err:
            logger.warning("query gold non eseguibile (%s): %s", key, err)
            cache[key] = None
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache

def stratified_sample(entries: list[dict], size: int, seed: int) -> list[dict]:
    """Campiona mantenendo le proporzioni fra i tipi di domanda del dataset completo."""
    by_kind: dict[str, list[dict]] = {}
    for entry in entries:
        by_kind.setdefault(question_kind(entry["query"]["sparql"]), []).append(entry)

    rng = random.Random(seed)
    sample: list[dict] = []
    for kind, group in sorted(by_kind.items()):
        quota = max(1, round(size * len(group) / len(entries)))
        sample.extend(rng.sample(group, min(quota, len(group))))

    # i tipi vanno mescolati fra loro: concatenati per gruppo, una run interrotta
    # restituirebbe solo i primi tipi in ordine alfabetico e quindi una stima distorta
    rng.shuffle(sample)
    return sample[:size]

def main() -> None:
    parser = argparse.ArgumentParser(description="valuta la pipeline su QALD-10")
    parser.add_argument("--sample", type=int, default=0, help="numero di domande (0 = tutte)")
    parser.add_argument("--seed", type=int, default=0, help="seme del campionamento, per ripetere lo stesso sottoinsieme")
    parser.add_argument("--target-kg", default="wikidata")
    parser.add_argument(
        "--gold",
        choices=("recorded", "executed"),
        default="recorded",
        help="risposte di riferimento: quelle registrate nel dataset o quelle della query gold eseguita ora",
    )
    parser.add_argument("--dry-run", action="store_true", help="mostra la composizione senza interrogare")
    args = parser.parse_args()

    entries = [e for e in load_dataset() if english_question(e)]
    if args.sample:
        entries = stratified_sample(entries, args.sample, args.seed)

    composition: dict[str, int] = {}
    for entry in entries:
        kind = question_kind(entry["query"]["sparql"])
        composition[kind] = composition.get(kind, 0) + 1
    print(f"domande da valutare: {len(entries)}  ({', '.join(f'{k}={v}' for k, v in sorted(composition.items()))})")
    if args.dry_run:
        return

    from cache.null_cache import NullCache
    from pipeline import KGPipeline

    regenerated_gold = executed_gold(entries) if args.gold == "executed" else {}
    if regenerated_gold:
        not_executable = sum(1 for v in regenerated_gold.values() if v is None)
        print(f"riferimento rigenerato eseguendo le query gold ({not_executable} non eseguibili, escluse)")
        entries = [e for e in entries if regenerated_gold.get(str(e.get("id"))) is not None]

    pipeline = KGPipeline(target_kg=args.target_kg, cache=NullCache())
    results: list[dict] = []
    started = time.time()

    for i, entry in enumerate(entries, start=1):
        question = english_question(entry)
        kind = question_kind(entry["query"]["sparql"])
        if regenerated_gold:
            value = regenerated_gold[str(entry.get("id"))]
            gold = value if isinstance(value, bool) else set(value)
        else:
            gold = gold_answers(entry)
        question_started = time.time()
        try:
            outcome = pipeline.run(question)
            ours = system_answers(outcome.results)
            error = ""
            query = outcome.query
        except Exception as err:
            ours, error, query = set(), f"{type(err).__name__}: {err}", ""
        precision, recall, f1 = score(gold, ours, pipeline.connector)

        results.append({
            "id": entry.get("id"), "kind": kind, "question": question, "f1": f1,
            "precision": precision, "recall": recall, "error": error,
            "gold": sorted(gold) if isinstance(gold, set) else gold,
            "ours": sorted(ours) if isinstance(ours, set) else ours,
            "query": query, "seconds": round(time.time() - question_started, 1),
        })
        print(f"[{i}/{len(entries)}] {kind:6} F1={f1:.2f}  {question[:64]}" + (f"  !{error[:40]}" if error else ""))

    macro_f1 = sum(r["f1"] for r in results) / len(results)
    print(f"\nmacro-F1: {macro_f1:.3f}   su {len(results)} domande, in {(time.time() - started) / 60:.1f} minuti")
    print("per tipo di domanda:")
    for kind in sorted(composition):
        group = [r for r in results if r["kind"] == kind]
        if group:
            print(f"  {kind:6} F1={sum(r['f1'] for r in group) / len(group):.3f}  ({len(group)} domande)")
    errors = sum(1 for r in results if r["error"])
    empty_answers = sum(1 for r in results if not r["error"] and not r["ours"])
    print(f"eccezioni: {errors}   risposte vuote: {empty_answers}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"qald10_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report.write_text(json.dumps({"macro_f1": macro_f1, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"dettaglio in {report}")

if __name__ == "__main__":
    main()
