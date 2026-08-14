"""
Valuta la pipeline sui benchmark QALD con la macro-F1.

Uso:
    python benchmarks/evaluate_qald.py --sample 30                  # campione stratificato
    python benchmarks/evaluate_qald.py                              # QALD-10 su wikidata
    python benchmarks/evaluate_qald.py --benchmark qald9plus        # QALD-9-plus su dbpedia
    python benchmarks/evaluate_qald.py --dry-run                    # solo composizione del dataset
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR = DATA_DIR / "evaluations"

# Wikidata cita le proprietà con un vocabolario unico; servono tutte e quattro le forme,
# perché contando solo wdt:/p: una query con qualificatori (ps:/pq:) risulterebbe "single",
# cioè facile, proprio perché è più complicata.
WIKIDATA_PREDICATES = re.compile(r"\b(?:wdt|p|ps|pq):P\d+")

# DBpedia non ha un vocabolario unico per i predicati, quindi ci si appoggia alla convenzione
# dell'ontologia: le proprietà hanno il nome locale in minuscolo, le classi in maiuscolo.
# La `a` isolata è la scorciatoia SPARQL per rdf:type ed è comunque un hop.
DBPEDIA_PREDICATES = re.compile(
    r"\b(?:dbo|dbp|onto|prop|dbpedia2|dct|dcterms|foaf|rdf|rdfs|skos|geo|gold):[a-z]\w*"
    r"|<https?://[^>]+/[a-z]\w*>"
    r"|(?<=\s)a(?=\s)"
)

@dataclass(frozen=True)
class Benchmark:
    """Un dataset QALD insieme al knowledge graph su cui è costruito."""
    label: str
    target_kg: str
    url: str
    filename: str
    predicates: re.Pattern[str]

    @property
    def dataset_path(self) -> Path:
        return DATA_DIR / self.filename

BENCHMARKS: dict[str, Benchmark] = {
    "qald10": Benchmark(
        label="QALD-10",
        target_kg="wikidata",
        url="https://raw.githubusercontent.com/KGQA/QALD-10/main/data/qald_10/qald_10.json",
        filename="qald_10.json",
        predicates=WIKIDATA_PREDICATES,
    ),
    # si valuta lo split di test, che è quello confrontabile con la letteratura: il train
    # è pensato per l'addestramento e qui non servirebbe, dato che la pipeline è zero-shot
    "qald9plus": Benchmark(
        label="QALD-9-plus (test)",
        target_kg="dbpedia",
        url="https://raw.githubusercontent.com/KGQA/QALD_9_plus/main/data/qald_9_plus_test_dbpedia.json",
        filename="qald_9_plus_test_dbpedia.json",
        predicates=DBPEDIA_PREDICATES,
    ),
}

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def load_dataset(benchmark: Benchmark) -> list[dict]:
    """Carica il dataset del benchmark, scaricandolo al primo utilizzo."""
    path = benchmark.dataset_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"scarico {benchmark.label} da {benchmark.url} ...")
        response = requests.get(benchmark.url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)
    return json.loads(path.read_text(encoding="utf-8"))["questions"]

def question_kind(sparql: str, predicates: re.Pattern[str] = WIKIDATA_PREDICATES) -> str:
    """Classifica la domanda dalla query gold, per stratificare il campione."""
    upper = sparql.upper()
    if re.search(r"\bASK\b", upper):
        return "ask"
    # COUNT vale come conteggio solo se sta nella proiezione: dentro un HAVING o un
    # ORDER BY è un criterio di selezione e la risposta attesa resta un elenco di entità
    projection = re.split(r"\bWHERE\b|\{", sparql, maxsplit=1, flags=re.IGNORECASE)[0]
    if re.search(r"\bCOUNT\s*\(", projection, flags=re.IGNORECASE):
        return "count"
    # il numero di predicati approssima il numero di hop: una sola tripla è una domanda diretta
    body = re.search(r"WHERE\s*\{(.*)\}", sparql, flags=re.IGNORECASE | re.DOTALL)
    triples = len(predicates.findall(body.group(1) if body else sparql))
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
    # i numeri vanno confrontati per valore: "4" e "4.0" sono la stessa risposta.
    # OverflowError va intercettato quanto ValueError: "Infinity" è un'etichetta che
    # esiste su Wikidata, float() la accetta e int() esplode.
    try:
        number = float(text)
        return str(int(number)) if number == int(number) else str(number)
    except (ValueError, OverflowError):
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
_DBPEDIA_RESOURCE = re.compile(r"^https?://dbpedia\.org/resource/(.+)$", re.IGNORECASE)

def _local_label(value: str) -> str | None:
    """Etichetta deducibile dall'URI stesso: su DBpedia il nome locale è già l'etichetta."""
    match = _DBPEDIA_RESOURCE.match(value)
    return normalize(unquote(match.group(1)).replace("_", " ")) if match else None

@dataclass(frozen=True)
class Answer:
    """Una risposta con le sue forme equivalenti; `uri` è l'identificatore, se ne ha uno."""
    uri: str | None
    forms: frozenset[str]

def _compatible(gold: Answer, ours: Answer) -> bool:
    """Due risposte coincidono se hanno lo stesso URI, o se un'etichetta fa da ponte con un letterale."""
    # l'etichetta non può accoppiare due URI diversi: su Wikidata è ambigua per costruzione
    # ("Mercury" è un pianeta e un elemento chimico) ed è proprio sugli omonimi che sbaglia
    # l'entity linking, quindi accettarla darebbe F1=1.0 all'errore che si vuole misurare
    if gold.uri and ours.uri:
        return gold.uri == ours.uri
    return bool(gold.forms & ours.forms)

def alias_sets(values: set[str], connector: Any = None) -> list[Answer]:
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

    items: list[Answer] = []
    # sorted() rende stabile l'ordine del report fra processi, dove l'iterazione di un
    # set dipende da PYTHONHASHSEED
    for value in sorted(values):
        forms = {value}
        match = _QID.search(value)
        if match and match.group(1).upper() in labels:
            forms.add(labels[match.group(1).upper()])
        if (local := _local_label(value)) is not None:
            forms.add(local)
        items.append(Answer(value if value.startswith(("http://", "https://")) else None, frozenset(forms)))
    return items

def _augment(start: int, adjacency: list[list[int]], assigned: dict[int, int]) -> bool:
    """Cerca un cammino aumentante partendo dalla risposta attesa `start`."""
    # la versione ricorsiva moriva di RecursionError oltre il migliaio di risposte attese,
    # e QALD-9-plus contiene una domanda che ne ha 1712: l'eccezione interrompeva l'intera
    # valutazione. Ogni elemento dello stack è [gold, posizione nell'adiacenza, arco percorso].
    visited: set[int] = set()
    stack: list[list[int]] = [[start, 0, -1]]
    while stack:
        frame = stack[-1]
        neighbours = adjacency[frame[0]]
        while frame[1] < len(neighbours):
            candidate = neighbours[frame[1]]
            frame[1] += 1
            if candidate in visited:
                continue
            visited.add(candidate)
            if candidate not in assigned:
                # cammino aumentante trovato: si riassegna a ritroso lungo lo stack
                assigned[candidate] = frame[0]
                for ancestor in stack[:-1]:
                    assigned[ancestor[2]] = ancestor[0]
                return True
            frame[2] = candidate
            stack.append([assigned[candidate], 0, -1])
            break
        else:
            stack.pop()
    return False

def _max_matching(gold_items: list[Answer], our_items: list[Answer]) -> int:
    """Accoppiamento massimo fra risposte attese e prodotte, con i cammini aumentanti di Kuhn."""
    # l'accoppiamento avido non è massimo: con gold [{a,b},{b}] e nostro [{b},{a}] appaia
    # la prima coppia e poi non trova più nulla, dimezzando l'F1 di una risposta esatta
    by_form: dict[str, list[int]] = {}
    for i, answer in enumerate(our_items):
        for form in answer.forms:
            by_form.setdefault(form, []).append(i)

    # l'adiacenza si precalcola: riscandire tutte le risposte prodotte a ogni passo del
    # cammino aumentante costa il quadrato, che su migliaia di risposte non è percorribile
    adjacency: list[list[int]] = []
    for gold in gold_items:
        reachable: dict[int, None] = {}
        for form in gold.forms:
            for i in by_form.get(form, ()):
                reachable[i] = None
        adjacency.append([i for i in reachable if _compatible(gold, our_items[i])])

    assigned: dict[int, int] = {}
    for gold_index in range(len(gold_items)):
        _augment(gold_index, adjacency, assigned)
    return len(assigned)

def score_items(gold_items: list[Answer], our_items: list[Answer]) -> tuple[float, float, float]:
    """F1 confrontando insiemi di forme equivalenti: due risposte coincidono se condividono una forma."""
    matched = _max_matching(gold_items, our_items)
    precision = matched / len(our_items)
    recall = matched / len(gold_items)
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

def has_usable_gold(gold: set[str] | bool | None) -> bool:
    """Un gold vuoto o non recuperabile non è valutabile: premierebbe una pipeline esplosa."""
    # con gold vuoto la convenzione QALD "nessuna attesa, nessuna prodotta" darebbe F1=1.0
    # anche a un crash, che pure produce zero righe. Il booleano False è invece un gold valido.
    if gold is None:
        return False
    return bool(gold) or isinstance(gold, bool)

def write_json(path: Path, payload: Any) -> None:
    """Scrittura atomica: un'interruzione a metà lascerebbe un file troncato e illeggibile."""
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def executed_gold(entries: list[dict], benchmark: Benchmark, provider: Any) -> dict[str, Any]:
    """Rigenera le risposte di riferimento eseguendo le query gold, e le memorizza su disco."""
    # le risposte registrate nei dataset QALD risalgono alla loro costruzione e i knowledge
    # graph sono cambiati: su QALD-10 il disallineamento è sistematico sui conteggi, su
    # QALD-9-plus un quarto delle domande non ha più alcuna risposta registrata. Confrontarsi
    # con la query gold eseguita oggi misura la qualità della nostra query, non l'età del dataset.
    path = benchmark.dataset_path
    cache_path = path.with_name(f"{path.stem}_executed.json")
    cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    from executors.sparql_executor import SPARQLExecutor

    # le query gold sono più pesanti delle nostre e si eseguono una volta sola: vale la
    # pena concedere più tempo del timeout della pipeline, invece di perdere domande
    executor = SPARQLExecutor(endpoint=provider.executor.endpoint, timeout=60)

    pending = [e for e in entries if str(e.get("id")) not in cache]
    failed = 0
    try:
        for i, entry in enumerate(pending, start=1):
            key = str(entry.get("id"))
            try:
                answers = system_answers(provider.connector.ground_results(executor.execute(entry["query"]["sparql"])))
                cache[key] = sorted(answers) if isinstance(answers, set) else answers
            except Exception as err:
                # il fallimento non va in cache: un 503 transitorio escluderebbe la domanda
                # da ogni run futura, presentandosi come invecchiamento del dataset
                logger.warning("query gold non eseguibile (%s): %s", key, err)
                failed += 1
            if i % 25 == 0:
                print(f"  gold rigenerato: {i}/{len(pending)}", flush=True)
                write_json(cache_path, cache)
    finally:
        write_json(cache_path, cache)
    if failed:
        print(f"  {failed} query gold non eseguibili: verranno ritentate alla prossima run")
    return cache

def stratified_sample(entries: list[dict], size: int, seed: int, predicates: re.Pattern[str]) -> list[dict]:
    """Campiona mantenendo le proporzioni fra i tipi di domanda del dataset completo."""
    by_kind: dict[str, list[dict]] = {}
    for entry in entries:
        by_kind.setdefault(question_kind(entry["query"]["sparql"], predicates), []).append(entry)

    # quote con il metodo dei resti massimi: arrotondando ogni quota per conto suo il
    # campione risultava più piccolo del richiesto (99 su 100), e un max(1, ...) dava alle
    # classi rare un peso che nel dataset non hanno, falsando la macro-F1 per tipo
    size = min(size, len(entries))
    exact = {kind: size * len(group) / len(entries) for kind, group in by_kind.items()}
    quotas = {kind: int(value) for kind, value in exact.items()}
    leftover = size - sum(quotas.values())
    for kind in sorted(exact, key=lambda k: (quotas[k] - exact[k], k))[:leftover]:
        quotas[kind] += 1

    rng = random.Random(seed)
    sample: list[dict] = []
    for kind, group in sorted(by_kind.items()):
        sample.extend(rng.sample(group, quotas[kind]))

    # i tipi vanno mescolati fra loro: concatenati per gruppo, una run interrotta
    # restituirebbe solo i primi tipi in ordine alfabetico e quindi una stima distorta
    rng.shuffle(sample)
    return sample

def main() -> None:
    parser = argparse.ArgumentParser(description="valuta la pipeline sui benchmark QALD")
    parser.add_argument(
        "--benchmark",
        choices=tuple(BENCHMARKS),
        default="qald10",
        help="dataset da valutare: qald10 su wikidata, qald9plus su dbpedia",
    )
    parser.add_argument("--sample", type=int, default=0, help="numero di domande (0 = tutte)")
    parser.add_argument("--seed", type=int, default=0, help="seme del campionamento, per ripetere lo stesso sottoinsieme")
    parser.add_argument(
        "--gold",
        choices=("recorded", "executed"),
        default="recorded",
        help="risposte di riferimento: quelle registrate nel dataset o quelle della query gold eseguita ora",
    )
    parser.add_argument("--dry-run", action="store_true", help="mostra la composizione senza interrogare")
    args = parser.parse_args()

    benchmark = BENCHMARKS[args.benchmark]
    entries = [e for e in load_dataset(benchmark) if english_question(e)]
    if args.sample:
        entries = stratified_sample(entries, args.sample, args.seed, benchmark.predicates)

    def describe(selection: list[dict]) -> str:
        """Composizione per tipo di domanda, come la stampa la riga di riepilogo."""
        counts: dict[str, int] = {}
        for entry in selection:
            kind = question_kind(entry["query"]["sparql"], benchmark.predicates)
            counts[kind] = counts.get(kind, 0) + 1
        return f"{len(selection)}  ({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))})"

    print(f"{benchmark.label} su {benchmark.target_kg}")
    if args.dry_run:
        print(f"domande nel campione: {describe(entries)}")
        print("(--dry-run non applica il filtro sul gold utilizzabile, che richiede l'endpoint)")
        return

    from cache.null_cache import NullCache
    from pipeline import KGPipeline
    from providers import build_provider

    provider = build_provider(benchmark.target_kg)
    executed = args.gold == "executed"
    regenerated_gold = executed_gold(entries, benchmark, provider) if executed else {}

    golds: dict[str, Any] = {}
    for entry in entries:
        key = str(entry.get("id"))
        if executed:
            value = regenerated_gold.get(key)
            golds[key] = set(value) if isinstance(value, list) else value
        else:
            golds[key] = gold_answers(entry)

    usable = [e for e in entries if has_usable_gold(golds[str(e.get("id"))])]
    if len(usable) != len(entries):
        missing = sum(1 for e in entries if golds[str(e.get("id"))] is None)
        empty = len(entries) - len(usable) - missing
        origin = "rigenerato eseguendo le query gold" if executed else "registrato nel dataset"
        print(f"riferimento {origin}: escluse {len(entries) - len(usable)} domande "
              f"({empty} senza risposte, {missing} con gold non recuperabile)")
        entries = usable

    # la composizione si stampa dopo il filtro: quella di prima annuncerebbe domande che
    # non verranno valutate, e il numero non corrisponderebbe a quello del report
    print(f"domande da valutare: {describe(entries)}")

    pipeline = KGPipeline(provider=provider, target_kg=benchmark.target_kg, cache=NullCache())
    results: list[dict] = []
    started = time.time()

    def save_report() -> None:
        """Salva su disco ciò che è stato valutato finora."""
        if not results:
            return
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(report_path, {
            "benchmark": benchmark.label, "target_kg": benchmark.target_kg, "gold": args.gold,
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
        errors = sum(1 for r in results if r["error"])
        empty_answers = sum(1 for r in results if not r["error"] and not r["ours"])
        print(f"eccezioni: {errors}   risposte vuote: {empty_answers}")

        save_report()
        print(f"dettaglio in {report_path}")

    report_path = REPORT_DIR / f"{args.benchmark}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        for i, entry in enumerate(entries, start=1):
            question = english_question(entry)
            kind = question_kind(entry["query"]["sparql"], benchmark.predicates)
            gold = golds[str(entry.get("id"))]
            question_started = time.time()
            try:
                outcome = pipeline.run(question)
                ours = system_answers(outcome.results)
                error = ""
                query = outcome.query
            except Exception as err:
                ours, error, query = set(), f"{type(err).__name__}: {err}", ""

            # un'eccezione non è una risposta: senza questo, su una domanda dal gold vuoto
            # la convenzione QALD "nessuna attesa, nessuna prodotta" premierebbe il crash
            precision, recall, f1 = (0.0, 0.0, 0.0) if error else score(gold, ours, pipeline.connector)

            results.append({
                "id": entry.get("id"), "kind": kind, "question": question, "f1": f1,
                "precision": precision, "recall": recall, "error": error,
                "gold": sorted(gold) if isinstance(gold, set) else gold,
                "ours": sorted(ours) if isinstance(ours, set) else ours,
                "query": query, "seconds": round(time.time() - question_started, 1),
            })
            print(f"[{i}/{len(entries)}] {kind:6} F1={f1:.2f}  {question[:64]}" + (f"  !{error[:40]}" if error else ""))

            # il salvataggio periodico copre ciò che il finally non può: un OOM killer, un
            # blackout, un kill -9. Su una run da ore è la differenza fra perdere venticinque
            # domande e perderle tutte, e la scrittura è atomica quindi non lascia file monchi
            if i % 25 == 0:
                save_report()
    finally:
        # una valutazione completa dura ore: un Ctrl-C o un'eccezione imprevista non devono
        # farne perdere il risultato parziale, che resta leggibile e dichiara quante domande
        # sono state effettivamente valutate sulle quante selezionate
        summarize()

if __name__ == "__main__":
    main()
