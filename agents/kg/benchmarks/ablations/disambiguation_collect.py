"""
Raccoglie i segnali di disambiguazione su QALD-10, senza LLM, per analisi offline.

Per ogni menzione salva i tre segnali (affinità col contesto, notorietà, posizione nella
ricerca) e quali candidati sono corretti secondo i QID della query gold.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

KG = Path(__file__).resolve().parents[2]
REPO = KG.parents[1]
EVALUATIONS_DIR = KG / "data" / "evaluations"
sys.path.insert(0, str(KG / "src"))
sys.path.insert(0, str(KG / "benchmarks"))
sys.path.insert(0, str(REPO))

from connectors.wikidata_connector import WikidataConnector
from models.embeddings import BGE_QUERY_INSTRUCTION, RETRIEVAL_MODEL_NAME, get_embedding_model
from evaluate_qald import BENCHMARKS, english_question, load_dataset, stratified_sample
from models.mention_extraction import extract_entity_mentions
from linkers.entity_linker import EntityLinker

OUT = Path(str(EVALUATIONS_DIR / "disambiguation_signals.json"))
SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 400

# la verità di riferimento sono i QID della query gold, quindi l'esperimento vive su wikidata
BENCHMARK = BENCHMARKS["qald10"]

def rescale(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    return [0.5] * len(values) if high == low else [(v - low) / (high - low) for v in values]

def main() -> None:
    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
    connector = WikidataConnector()
    linker = EntityLinker(connector=connector)
    model = get_embedding_model(RETRIEVAL_MODEL_NAME)
    dataset = [e for e in load_dataset(BENCHMARK) if english_question(e)]
    entries = stratified_sample(dataset, SIZE, 0, BENCHMARK.predicates)
    collected: list[dict] = []
    # l'ablazione vive sulle sole menzioni disambiguabili, quindi il suo tasso di successo
    # è condizionato: contare anche gli scarti separa un errore di scelta da uno di ricerca
    discarded: Counter[str] = Counter()

    for n, entry in enumerate(entries, start=1):
        question = english_question(entry)
        gold = {q.upper() for q in re.findall(r"\bQ\d+\b", entry["query"]["sparql"])}
        if not gold:
            discarded["domande senza QID nella query gold"] += 1
            continue
        try:
            mentions = extract_entity_mentions(question)
        except Exception:
            discarded["estrazione delle menzioni fallita"] += 1
            continue

        for raw_mention in mentions:
            try:
                mention, found = linker._search_mention(raw_mention.strip())
            except Exception:
                discarded["ricerca dei candidati fallita"] += 1
                continue
            cands = [c for c in found if connector.is_valid_candidate(c)]
            if not cands:
                discarded["nessun candidato trovato"] += 1
                continue
            if len(cands) < 2:
                discarded["un solo candidato, nulla da disambiguare"] += 1
                continue
            if not ({c.id.upper() for c in cands} & gold):
                discarded["candidato corretto assente dai risultati"] += 1
                continue

            descriptions = [c.description or "" for c in cands]
            vectors = model.encode(
                [BGE_QUERY_INSTRUCTION + question] + descriptions,
                convert_to_numpy=True, normalize_embeddings=True,
            )
            sitelinks = connector.candidate_prominence(cands)
            collected.append({
                "question": question,
                "mention": mention,
                "ids": [c.id for c in cands],
                "labels": [c.label for c in cands],
                "descriptions": descriptions,
                "correct": [c.id.upper() in gold for c in cands],
                "similarities": [float(s) if descriptions[i] else 0.0
                                 for i, s in enumerate(vectors[1:] @ vectors[0])],
                "sitelinks": [sitelinks.get(c.id, 0.0) for c in cands],
            })

        if n % 25 == 0:
            print(f"  ...{n}/{len(entries)} domande, {len(collected)} menzioni raccolte", flush=True)
            OUT.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")

    OUT.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")
    print(f"\nmenzioni raccolte: {len(collected)} -> {OUT}")
    if discarded:
        print("scartate:")
        for reason, count in discarded.most_common():
            print(f"  {count:4}  {reason}")
    if discarded["candidato corretto assente dai risultati"]:
        # il riferimento sono i QID dell'intera query gold: una menzione che il gold non
        # usa affatto finisce in quella riga pur senza essere un fallimento della ricerca
        print("nota: 'candidato corretto assente' è un limite superiore ai fallimenti della "
              "ricerca, perché include le menzioni che la query gold non usa")

if __name__ == "__main__":
    main()
