"""
Valutatore semantico (LLM-as-a-judge) per il benchmark del Planner Agent.

Legge i risultati generati in benchmark_results.json e interroga un LLM Giudice (Gemma)
per la valutazione testuale. Poi passa il testo a un modello locale (Ollama) per
l'estrazione rigorosa del JSON.
Salva in modo incrementale su semantic_eval_results.json.
"""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

# Bootstrap di sys.path
src_dir: Path = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from configs.settings import settings
from http_client import close_http_client
from llm_client import LLMClient

logger = logging.getLogger("semantic_eval")
logging.basicConfig(level=logging.INFO, format="%(message)s")


# --- CONFIGURAZIONE GIUDICE (Ragionamento) ---
JUDGE_PROVIDER = "gemini"
JUDGE_MODEL = "gemma-4-31b-it"

# --- CONFIGURAZIONE ESTRATTORE (Parsing JSON) ---
EXTRACTOR_PROVIDER = "ollama"
EXTRACTOR_MODEL = "llama3.2"  # Inserisci qui il modello locale che preferisci usare per il parsing


# --- FILTRI DI ESECUZIONE ---
TARGET_MODELS: list[str] = [""]          
TARGET_CONTEXT_MODES: list[str] = []   
TARGET_TEST_IDS: list[str] = []        


BENCHMARK_DIR: Path = Path(__file__).resolve().parent
DATASET_PATH: Path = BENCHMARK_DIR / "benchmark_dataset.json"
RESULTS_PATH: Path = BENCHMARK_DIR / "benchmark_results.json"
EVAL_RESULTS_PATH: Path = BENCHMARK_DIR / "semantic_eval_results.json"
PROMPT_PATH: Path = settings.prompts_dir / "semantic_eval.txt"

RATE_LIMIT_DELAY_SECONDS: float = 2.0


# --- UTILITY DI PERSISTENZA ---

def _load_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return json.loads(content)
    return {}

def _save_evaluations(evals: dict[str, Any]) -> None:
    EVAL_RESULTS_PATH.write_text(json.dumps(evals, ensure_ascii=False, indent=2), encoding="utf-8")


# --- ESECUZIONE SINGOLA VALUTAZIONE (CASCATA LLM) ---

async def _evaluate_single(
    result_key: str, 
    record: dict[str, Any], 
    test_case: dict[str, Any], 
    llm: LLMClient
) -> dict[str, Any] | None:
    """
    Esegue la valutazione in due step:
    1. Chiede a Gemma di generare il testo di valutazione.
    2. Chiede a Ollama di estrarre e validare il JSON da quel testo.
    """
    plan_output = record.get("plan_output") or {}
    
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    judge_prompt = prompt_template.format(
        question=test_case["question"],
        intent=test_case.get("intent", "new_plan"),
        gathered_context=json.dumps(plan_output.get("gathered_context") or {}, ensure_ascii=False),
        context_errors=json.dumps(plan_output.get("context_errors") or []),
        previous_plan=json.dumps(test_case.get("previous_plan") or {}, ensure_ascii=False),
        plan_output=json.dumps(plan_output, ensure_ascii=False)
    )

    # --- STEP 1: RAGIONAMENTO (Gemma) ---
    settings.llm_provider = JUDGE_PROVIDER
    if JUDGE_PROVIDER == "gemini":
        settings.gemini_model = JUDGE_MODEL

    raw_evaluation_text = await llm.generate(judge_prompt, json_mode=False)
    
    if not raw_evaluation_text:
        logger.error(f"  [error] Gemma ha restituito un output vuoto.")
        return None

    logger.info("    -> Ragionamento completato da Gemma. Passo l'estrazione a Ollama...")

    # --- STEP 2: ESTRAZIONE JSON (Ollama) ---
    settings.llm_provider = EXTRACTOR_PROVIDER
    if EXTRACTOR_PROVIDER == "ollama":
        settings.ollama_model = EXTRACTOR_MODEL

    intent_value = test_case.get("intent", "new_plan")

    extractor_prompt = f"""
    You are a data extraction assistant. Extract the rationales and scores from the following evaluation text.
    Convert it into a strictly valid JSON object. Do not add any conversational text.

    EVALUATION TEXT TO PARSE:
    {raw_evaluation_text}

    CURRENT INTENT:
    {intent_value}

    REQUIRED JSON FORMAT:
    {{
      "groundedness_rationale": "string",
      "groundedness_score": integer (1-5),
      "semantic_adherence_rationale": "string",
      "semantic_adherence_score": integer (1-5),
      "human_feasibility_rationale": "string",
      "human_feasibility_score": integer (1-5),
      "granularity_rationale": "string",
      "granularity_score": integer (1-5),
      "replanning_consistency_rationale": "string or null (must be null if CURRENT INTENT is new_plan)",
      "replanning_consistency_score": integer (1-5) or null (must be null if CURRENT INTENT is new_plan)
    }}
    """

    # extract_json chiama Ollama (con json_mode=True) e parsa il risultato
    return await llm.extract_json(extractor_prompt)


# --- MAIN LOOP ---

async def main() -> None:
    logger.info("\n==================================================")
    logger.info("=== Avvio Valutatore Semantico (Architettura a Cascata) ===")
    logger.info(f"=== Giudice (Logica): {JUDGE_PROVIDER} | {JUDGE_MODEL} ===")
    logger.info(f"=== Estrattore (JSON): {EXTRACTOR_PROVIDER} | {EXTRACTOR_MODEL} ===")
    logger.info("==================================================\n")

    if not DATASET_PATH.exists() or not RESULTS_PATH.exists():
        logger.error("File di dataset o risultati mancanti. Esegui prima run_benchmarks.py")
        return

    dataset_list = _load_json(DATASET_PATH)
    dataset_map = {item["id"]: item for item in dataset_list} # type: ignore
    
    results: dict[str, Any] = _load_json(RESULTS_PATH) # type: ignore
    evals: dict[str, Any] = _load_json(EVAL_RESULTS_PATH) # type: ignore

    tests_to_run: list[tuple[str, dict[str, Any]]] = []
    for key, record in results.items():
        test_id = record.get("test_id", "")
        model_name = record.get("model_name", "")
        context_mode = record.get("context_gathering_mode", "")

        if TARGET_MODELS and model_name not in TARGET_MODELS:
            continue
        if TARGET_CONTEXT_MODES and context_mode not in TARGET_CONTEXT_MODES:
            continue
        if TARGET_TEST_IDS and test_id not in TARGET_TEST_IDS:
            continue
            
        if record.get("expected_domain") == "unknown" or record.get("error") is not None or not (record.get("plan_output") or {}).get("days"):
            continue

        tests_to_run.append((key, record))

    total_tests = len(tests_to_run)
    if total_tests == 0:
        logger.info("Nessun test corrispondente ai filtri specificati (o test già scartati).")
        return

    llm = LLMClient(verbose=False)
    
    current_test_idx = 0
    for key, record in tests_to_run:
        current_test_idx += 1
        progress_pct = round(100 * current_test_idx / total_tests, 1)

        if key in evals and "error" not in evals[key]:
            logger.info("    [%d/%d - %s%%] [skip] %s già valutato", current_test_idx, total_tests, progress_pct, key)
            continue

        logger.info("    [%d/%d - %s%%] [run]  Valutazione %s", current_test_idx, total_tests, progress_pct, key)
        
        test_case = dataset_map.get(record["test_id"])
        if not test_case:
            logger.error("    [%d/%d - %s%%] [error] Test case %s non trovato", current_test_idx, total_tests, progress_pct, record["test_id"])
            continue

        try:
            evaluation = await _evaluate_single(key, record, test_case, llm)
            
            if evaluation is None:
                raise ValueError("Il Giudice o l'Estrattore hanno fallito.")
                
            evals[key] = evaluation
            _save_evaluations(evals)

        except Exception as err:
            logger.error("    [%d/%d - %s%%] [error] Fallimento su %s: %s", current_test_idx, total_tests, progress_pct, key, err)
            evals[key] = {"error": str(err)}
            _save_evaluations(evals)

        await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)

    logger.info("\n>>> Valutazione completata. Risultati salvati in %s", EVAL_RESULTS_PATH.name)

async def run_all() -> None:
    try:
        await main()
    finally:
        await close_http_client()

if __name__ == "__main__":
    asyncio.run(run_all())