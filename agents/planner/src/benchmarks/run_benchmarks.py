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


# Stesso bootstrap di sys.path usato in main.py, per poter lanciare lo
# script sia da root ("python src/run_benchmarks.py") sia da dentro src/.
src_dir: Path = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from api.schemas import QueryRequest  
from configs.settings import settings  
from http_client import close_http_client  
from pipeline import PlannerPipeline  
from state import plan_state_store  

from unittest.mock import patch
from validators import validate_draft as original_validate_draft

logger = logging.getLogger("planner_benchmark")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# --- CONFIGURAZIONE ---

# Ogni valore deve corrispondere a "gemini", "ollama", oppure a una chiave
# presente in settings.openai_providers (.env, OPENAI_PROVIDERS). Le due
# varianti OpenRouter qui sotto assumono due chiavi separate nel JSON con lo
# stesso base_url/api_key e "model" diverso.
MODELS_TO_TEST: list[str] = ["openrouter_gpt_oss"]

CONTEXT_MODES_TO_TEST: list[Literal["deterministic", "react", "none"]] = ["none"]

BENCHMARK_DIR: Path = Path(__file__).resolve().parent
DATASET_PATH: Path = BENCHMARK_DIR / "benchmark_dataset.json"
RESULTS_PATH: Path = BENCHMARK_DIR / "benchmark_results.json"

RATE_LIMIT_DELAY_SECONDS: float = 30


# --- UTILITY DI PERSISTENZA ---

def _load_dataset() -> list[dict[str, Any]]:
    """
    Carica il golden dataset dei test da disco.

    Returns:
        list[dict[str, Any]]: I test case (id, intent, question, expected_domain, ...).

    Raises:
        FileNotFoundError: Se il dataset (Fase 2) non è ancora stato creato.
    """
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Golden dataset non trovato in {DATASET_PATH} (va creato nella Fase 2)."
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
    Recupera il nome effettivo del modello in base alla configurazione.
    """
    if provider == "ollama":
        return settings.ollama_model
    elif provider == "gemini":
        return settings.gemini_model
    else:
        # Per i provider custom in openai_providers
        provider_config = settings.openai_providers.get(provider, {})
        return provider_config.get("model", provider)


# --- ESECUZIONE SINGOLO TEST ---

async def _run_single_test(
    pipeline: PlannerPipeline, test: dict[str, Any], provider_name: str, context_mode: str
) -> dict[str, Any]:
    """
    Esegue un singolo test case contro il modello/modalità di context
    gathering correnti, gestendo l'iniezione dello stato per i test 'replan'.
    """
    test_id: str = test["id"]
    expected_domain: str = test["expected_domain"]
    intent: str = test.get("intent", "new_plan")
    
    actual_model_name: str = _get_actual_model_name(provider_name)

    val_errors_history: list[list[str]] = []

    def tracking_validate_draft(draft: Any, domain: str) -> list[str]:
        errors = original_validate_draft(draft, domain)
        if errors:
            val_errors_history.append(list(errors))
        return errors

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
        session_id: str | None = None
        if intent == "replan":
            session_id = "bench_session"
            plan_state_store.save(
                session_id=session_id,
                domain=expected_domain, # type: ignore
                question="mock",
                draft=test["previous_plan"],
            )

        request = QueryRequest(question=test["question"], session_id=session_id)
        
        with patch("pipeline.validate_draft", new=tracking_validate_draft):
            response = await pipeline.run(request)

        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["validation_errors_history"] = val_errors_history
        
        result["plan_output"] = response.model_dump(mode="json")

        if expected_domain == "unknown":
            result["success"] = response.domain == "unknown"
        else:
            result["success"] = response.domain == expected_domain and len(response.days) > 0

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
    logger.info("Fallback locale disattivato per garantire benchmark puri.")

    try:
        for model_name in MODELS_TO_TEST:
            settings.llm_provider = model_name
            pipeline: PlannerPipeline = PlannerPipeline(verbose=False)
            logger.info("=== Provider/modello corrente: %s ===", model_name)

            for context_mode in CONTEXT_MODES_TO_TEST:
                settings.context_gathering_mode = context_mode
                logger.info("--- Context gathering: %s ---", context_mode)

                for test in dataset:
                    actual_model = _get_actual_model_name(model_name)
                    key: str = _result_key(test["id"], actual_model, context_mode)

                    if key in results:
                        if results[key].get("error") is None:
                            logger.info("  [skip] %s già processato con successo", key)
                            continue
                        else:
                            logger.info("  [retry] %s riprovo test precedentemente fallito", key)

                    logger.info("  [run] %s", key)
                    result: dict[str, Any] = await _run_single_test(pipeline, test, model_name, context_mode)

                    results[key] = result
                    _save_results(results)

                    if result["error"] is not None:
                        logger.error(
                            "  [error] test fallito su %s, proseguo col prossimo. Errore: %s",
                            key, result["error"],
                        )

                    if model_name != "ollama":
                        await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)

        logger.info("Benchmark completato: %d risultati totali in %s", len(results), RESULTS_PATH)
    finally:
        await close_http_client()


if __name__ == "__main__":
    asyncio.run(main())