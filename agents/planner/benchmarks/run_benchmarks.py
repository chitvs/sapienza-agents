"""
Benchmark runner per il Planner Agent.

Cicla il golden dataset (benchmarks/benchmark_dataset.json) contro una lista
di provider/modelli configurabile (MODELS_TO_TEST), eseguendo la pipeline per
ogni combinazione test x modello. I risultati vengono salvati in modo
incrementale su benchmarks/benchmark_results.json: le combinazioni già
processate vengono skippate, quindi uno stop (manuale o per rate limit) non
fa perdere lavoro già fatto.
"""

import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Literal
from datetime import datetime, timezone


project_root: Path = Path(__file__).resolve().parent.parent
src_dir: Path = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from api.schemas import QueryRequest  
from configs.settings import settings  
from http_client import close_http_client  
from pipeline import PlannerPipeline, REPLAN_FAILURE_NOTE  

from unittest.mock import patch
from validators import validate_draft as original_validate_draft

logger = logging.getLogger("planner_benchmark")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# --- CONFIGURAZIONE ---

# Ogni valore deve corrispondere a "gemini", "ollama" oppure "openrouter".

# MODELS_TO_TEST = [
#     # Modelli Google
#     ("gemini", "gemini-3.6-flash"),
    
#     # Modelli Locali (Ollama)
#     ("ollama", "qwen2.5:1.5b"),
#     ("ollama", "qwen2.5:3b"),
#     ("ollama", "llama3.2"),
    
#     # Modelli Remoti Open-Source (OpenRouter)
#     ("openrouter", "openai/gpt-oss-20b:free")
# ]

MODELS_TO_TEST = [
    ("gemini", "gemini-3.5-flash-lite"),
    ("gemini", "gemini-3.6-flash"),
    ("ollama", "llama3.2"),
    ("ollama", "ministral-3:3b"),
    ("ollama", "qwen3:1.7b"),
    ("ollama", "qwen3:4b"),
    ("ollama", "phi4-mini"),
    #("openrouter", "openai/gpt-oss-20b:free"),
    #("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    #("openrouter", "nvidia/nemotron-3.5-lightning:free"),
    #("openrouter", "nvidia/nemotron-3.5-lightning:free"),
    #("openrouter", "poolside/laguna-s-2.1:free"),
    #("openrouter", "z-ai/glm-5.2:free"),
]

CONTEXT_MODES_TO_TEST: list[Literal["deterministic", "react", "none"]] = ["none"]

# In caso di test deterministc decidere quali agenti esterni chiamare.
DETERMINISTIC_ROUTING_MAP = {
    "travel": ["kg_agent", "multiapi_agent"],
    "study": [],
    "routine": [],
    "unknown": []
}

BENCHMARK_DIR: Path = Path(__file__).resolve().parent
DATASET_PATH: Path = BENCHMARK_DIR / "data" / "benchmark_dataset.json"
RESULTS_PATH: Path = BENCHMARK_DIR / "data" / "benchmark_results.json"

RATE_LIMIT_DELAY_SECONDS: float = 15


# --- UTILITY DI PERSISTENZA ---

def _load_dataset() -> list[dict[str, Any]]:
    """
    Carica il golden dataset dei test da disco.

    Returns:
        list[dict[str, Any]]: I test case (id, intent, question, expected_domain, ...).

    Raises:
        FileNotFoundError: Se il dataset non è ancora stato creato.
    """
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Golden dataset non trovato in {DATASET_PATH}."
        )
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _load_results() -> dict[str, Any]:
    """
    Carica i risultati già processati, se presenti (database storico usato
    per lo skip delle combinazioni già completate).

    Returns:
        dict[str, Any]: Mappa "test_id::model_name" -> risultato del test.
    """
    if RESULTS_PATH.exists():
        content = RESULTS_PATH.read_text(encoding="utf-8").strip()
        if content:
            return json.loads(content)
    return {}


def _save_results(results: dict[str, Any]) -> None:
    """
    Scrive fisicamente i risultati su disco. Va chiamata dopo ogni singolo
    test per rendere la run interrompibile e ripartibile senza perdite.

    Args:
        results (dict[str, Any]): La mappa completa dei risultati accumulati finora.
    """
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def _result_key(test_id: str, model_name: str, context_mode: str) -> str:
    """
    Costruisce la chiave univoca (test_id, modello, context mode) usata come
    indice nel database storico dei risultati.

    Args:
        test_id (str): L'identificativo del test case.
        model_name (str): Il provider/modello testato.
        context_mode (str): La modalità di context gathering testata.

    Returns:
        str: La chiave composta "test_id::model_name::context_mode".
    """
    return f"{test_id}::{model_name}::{context_mode}"

def _get_actual_model_name(provider: str) -> str:
    """
    Recupera il nome effettivo del modello in base alla configurazione corrente,
    preservando strettamente la logica storica (ripulendolo da prefissi es. 'openai/'
    e suffissi es. ':free') affinché l'ID calcolato per il benchmark corrisponda
    sempre ai file storici già salvati.
    """
    if provider == "ollama":
        raw_name = settings.ollama_model
    elif provider == "gemini":
        raw_name = settings.gemini_model
    elif provider == "openrouter":
        raw_name = settings.parsed_openrouter_models[0] if settings.parsed_openrouter_models else ""
    else:
        raw_name = provider
        
    clean_name = raw_name.split("/")[-1] if "/" in raw_name else raw_name
    
    if clean_name.endswith(":free"):
        clean_name = clean_name[:-5]
        
    return clean_name


# --- ESECUZIONE SINGOLO TEST ---

async def _run_single_test(
    pipeline: PlannerPipeline, test: dict[str, Any], provider_name: str, context_mode: str
) -> dict[str, Any]:
    """
    Esegue un singolo test case contro il modello/modalità di context
    gathering correnti, passando direttamente il piano precedente nei test
    di replanning.
    """
    test_id: str = test["id"]
    expected_domain: str = test["expected_domain"]
    intent: str = test.get("intent", "new_plan")

    actual_model_name: str = _get_actual_model_name(provider_name)

    val_errors_history: list[list[str]] = []

    def tracking_validate_draft(draft: Any, domain: str, previous_plan: dict[str, Any] | None = None) -> list[str]:
        errors = original_validate_draft(draft, domain, previous_plan)
        if errors:
            val_errors_history.append(list(errors))
        return errors

    original_extract = pipeline.prompts.extract_json

    async def delayed_extract(*args, **kwargs):
        if provider_name != "ollama":
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
        return await original_extract(*args, **kwargs)

    result: dict[str, Any] = {
        "test_id": test_id,
        "model_name": actual_model_name,
        "context_gathering_mode": context_mode,
        "expected_intent": intent,
        "expected_domain": expected_domain,
        "success": False,
        "timestamp": None,
        "validation_errors_history": [],
        "error": None,
        "traceback": None,
        "plan_output": None,
    }

    try:
        request_kwargs: dict[str, Any] = {
            "question": test["question"],
        }

        if context_mode == "deterministic":
            # Prende i tool dal dataset se specificati, altrimenti usa la mappa del Supervisor
            request_kwargs["allowed_tools"] = test.get(
                "allowed_tools", 
                DETERMINISTIC_ROUTING_MAP.get(expected_domain, [])
            )

        if intent == "replan":
            request_kwargs["previous_plan"] = test["previous_plan"]
            request_kwargs["previous_domain"] = expected_domain

        request = QueryRequest(**request_kwargs)

        with patch("pipeline.validate_draft", new=tracking_validate_draft), \
             patch.object(pipeline.prompts, "extract_json", side_effect=delayed_extract):
            response = await pipeline.run(request)

        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["validation_errors_history"] = val_errors_history
        
        result["plan_output"] = response.model_dump(mode="json")

        if expected_domain == "unknown":
            result["success"] = response.domain == "unknown"
        else:
            result["success"] = response.domain == expected_domain and len(response.days) > 0

            if intent == "replan" and result["success"]:
                notes = result["plan_output"].get("contingency_notes") or []
                if REPLAN_FAILURE_NOTE in notes:
                    result["success"] = False

    except Exception as err:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["error"] = f"{err.__class__.__name__}: {err}"
        result["traceback"] = traceback.format_exc()
        logger.exception("Errore durante il test %s su modello %s", test_id, actual_model_name)

    return result


# --- MAIN LOOP ---

async def main() -> None:
    """
    Entrypoint del benchmark: itera modelli x modalità di context gathering x
    test case, riprendendo dallo stato salvato su disco e gestendo i rate
    limit dei provider cloud.
    """
    dataset: list[dict[str, Any]] = _load_dataset()
    results: dict[str, Any] = _load_results()

    settings.enable_local_fallback = False
    logger.info(">>> Fallback locale disattivato per garantire benchmark puri.")

    total_tests = len(MODELS_TO_TEST) * len(CONTEXT_MODES_TO_TEST) * len(dataset)
    current_test_idx = 0

    try:
        for provider_name, model_name in MODELS_TO_TEST:
    
            settings.llm_provider = provider_name
            
            if provider_name == "gemini":
                settings.gemini_model = model_name
            elif provider_name == "ollama":
                settings.ollama_model = model_name
            elif provider_name == "openrouter":
                settings.openrouter_models = model_name


            pipeline: PlannerPipeline = PlannerPipeline(verbose=False)
            logger.info("\n==================================================")
            logger.info("=== Provider: %s | Modello: %s ===", provider_name, model_name)
            logger.info("==================================================")

            for context_mode in CONTEXT_MODES_TO_TEST:
                settings.context_gathering_mode = context_mode
                logger.info("  [Context Mode] -> %s", context_mode)

                for test in dataset:
                    current_test_idx += 1
                    progress_pct = round(100 * current_test_idx / total_tests, 1)
                    actual_model = _get_actual_model_name(provider_name)
                    key: str = _result_key(test["id"], actual_model, context_mode)

                    if key in results:
                        if results[key].get("error") is None:
                            logger.info("    [%d/%d - %s%%] [skip] %s già processato", current_test_idx, total_tests, progress_pct, key)
                            continue
                        else:
                            logger.info("    [%d/%d - %s%%] [retry] %s riprovo test fallito in precedenza", current_test_idx, total_tests, progress_pct, key)

                    logger.info("    [%d/%d - %s%%] [run]  Esecuzione %s", current_test_idx, total_tests, progress_pct, key)
                    result: dict[str, Any] = await _run_single_test(pipeline, test, provider_name, context_mode)

                    results[key] = result
                    _save_results(results)

                    if result["error"] is not None:
                        logger.error(
                            "    [%d/%d - %s%%] [error] Test fallito su %s. Errore: %s",
                            current_test_idx, total_tests, progress_pct, key, result["error"]
                        )

        logger.info("\n>>> Benchmark completato con successo: %d risultati totali salvati in %s", len(results), RESULTS_PATH)
    finally:
        await close_http_client()


if __name__ == "__main__":
    asyncio.run(main())