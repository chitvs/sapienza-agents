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

from api.schemas import QueryRequest  # noqa: E402
from configs.settings import settings  # noqa: E402
from http_client import close_http_client  # noqa: E402
from pipeline import PlannerPipeline  # noqa: E402
from state import plan_state_store  # noqa: E402

logger = logging.getLogger("planner_benchmark")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# --- CONFIGURAZIONE ---

# Ogni valore deve corrispondere a "gemini", "ollama", oppure a una chiave
# presente in settings.openai_providers (.env, OPENAI_PROVIDERS). Le due
# varianti OpenRouter qui sotto assumono due chiavi separate nel JSON con lo
# stesso base_url/api_key e "model" diverso.
MODELS_TO_TEST: list[str] = ["ollama"]

CONTEXT_MODES_TO_TEST: list[Literal["deterministic", "react", "none"]] = ["none"]

BENCHMARK_DIR: Path = Path(__file__).resolve().parent
DATASET_PATH: Path = BENCHMARK_DIR / "benchmark_dataset.json"
RESULTS_PATH: Path = BENCHMARK_DIR / "benchmark_results.json"

RATE_LIMIT_DELAY_SECONDS: float = 3.5


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


# --- ESECUZIONE SINGOLO TEST ---

async def _run_single_test(
    pipeline: PlannerPipeline, test: dict[str, Any], model_name: str, context_mode: str
) -> dict[str, Any]:
    """
    Esegue un singolo test case contro il modello/modalità di context
    gathering correnti, gestendo l'iniezione dello stato per i test 'replan'.

    Args:
        pipeline (PlannerPipeline): La pipeline già istanziata per il modello corrente.
        test (dict[str, Any]): Il test case dal golden dataset.
        model_name (str): Il provider/modello corrente (già impostato su settings.llm_provider).
        context_mode (str): La modalità di context gathering corrente (già impostata su settings).

    Returns:
        dict[str, Any]: Il risultato del test con le metriche richieste.
    """
    test_id: str = test["id"]
    expected_domain: str = test["expected_domain"]
    intent: str = test.get("intent", "new_plan")
    question: str = test["question"]

    result: dict[str, Any] = {
        "test_id": test_id,
        "question": question,
        "model_name": model_name,
        "context_gathering_mode": context_mode,
        "expected_intent": intent,
        "expected_domain": expected_domain,
        "actual_domain": None,
        "actual_replanned": None,
        "plan_title": None,
        "plan_summary": None,
        "contingency_notes": None,
        "execution_time_ms": None,
        "confidence": None,
        "success": False,
        "timestamp": None,
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
                domain=expected_domain,
                question="mock",
                draft=test["previous_plan"],
            )

        request = QueryRequest(question=question, session_id=session_id)
        response = await pipeline.run(request)

        result["actual_domain"] = response.domain
        result["actual_replanned"] = response.replanned
        result["plan_title"] = response.title
        result["plan_summary"] = response.summary
        result["contingency_notes"] = response.contingency_notes
        result["execution_time_ms"] = response.execution_time_ms
        result["confidence"] = response.confidence
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["plan_output"] = response.model_dump(mode="json")

        if expected_domain == "unknown":
            result["success"] = response.domain == "unknown"
        else:
            result["success"] = response.domain == expected_domain and len(response.days) > 0

    except Exception as err:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["error"] = f"{err.__class__.__name__}: {err}"
        result["traceback"] = traceback.format_exc()
        logger.exception("Errore durante il test %s su modello %s", test_id, model_name)

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

    try:
        for model_name in MODELS_TO_TEST:
            settings.llm_provider = model_name
            pipeline: PlannerPipeline = PlannerPipeline(verbose=False)
            logger.info("=== Provider/modello corrente: %s ===", model_name)

            for context_mode in CONTEXT_MODES_TO_TEST:
                settings.context_gathering_mode = context_mode
                logger.info("--- Context gathering: %s ---", context_mode)

                for test in dataset:
                    key: str = _result_key(test["id"], model_name, context_mode)

                    if key in results:
                        logger.info("  [skip] %s già processato", key)
                        continue

                    logger.info("  [run] %s", key)
                    result: dict[str, Any] = await _run_single_test(pipeline, test, model_name, context_mode)

                    results[key] = result
                    _save_results(results)

                    if result["error"] is not None:
                        logger.error(
                            "  [stop] errore su %s, run interrotta per permettere una ripresa pulita: %s",
                            key, result["error"],
                        )
                        sys.exit(0)

                    if model_name != "ollama":
                        await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)

        logger.info("Benchmark completato: %d risultati totali in %s", len(results), RESULTS_PATH)
    finally:
        await close_http_client()


if __name__ == "__main__":
    asyncio.run(main())