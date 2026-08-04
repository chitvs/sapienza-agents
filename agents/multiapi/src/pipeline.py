import json
import re
import logging
from typing import Any
from pathlib import Path

import requests

from configs.settings import settings
from providers.weather_provider import WeatherProvider
from providers.exchange_provider import ExchangeProvider

logger = logging.getLogger("multiapi_pipeline")


class MultiApiPipeline:
    """pipeline dell'agente multiapi: classifica l'intent, estrae i parametri e chiama il provider giusto."""

    def __init__(self, verbose: bool = False):
        self.weather = WeatherProvider()
        self.exchange = ExchangeProvider()
        self.verbose = verbose
        self._prompts_cache: dict[str, str] = {}

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    # -- llm helpers (self-contained, nessuna dipendenza da shared) ----

    def _llm_generate(self, prompt: str, temperature: float = 0.0) -> str:
        """chiama ollama /api/generate e restituisce la risposta grezza."""
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,  # aspetta la risposta completa e non stampa token per token
            "options": {"temperature": temperature},  # temperatura llm 0 per risposte deterministiche
        }
        resp = requests.post(url, json=payload, timeout=settings.ollama_timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    @staticmethod
    def _clean_json(raw: str) -> str:
        """rimuove eventuali blocchi markdown (```json ... ```) dalla risposta llm."""
        if not raw:
            return ""
        cleaned = raw.strip()
        if "```" in cleaned:
            match = re.search(
                r"```(?:json)?\s*(.*?)\s*```",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                return match.group(1).strip()
        return cleaned

    def _load_prompt(self, filename: str) -> str:
        """carica un template prompt dalla cartella prompts (con cache)."""
        if filename not in self._prompts_cache:
            path = settings.prompts_dir / filename
            self._prompts_cache[filename] = path.read_text(encoding="utf-8")
        return self._prompts_cache[filename]

    def _llm_extract_json(self, prompt_file: str, question: str) -> dict | None:
        """helper generico: carica un prompt, lo invia al llm, parsa il json di risposta."""
        template = self._load_prompt(prompt_file)
        prompt = template.format(question=question)
        raw = self._llm_generate(prompt)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log(f"  [warn] impossibile parsare json: {cleaned}")
            return None

    # ----- classificatore di intent -----

    def _classify_intent(self, question: str) -> str:
        """usa il llm per classificare la domanda in un intent supportato."""
        self._log("\n[info] [step] classificazione intent via llm")
        data = self._llm_extract_json("classify_intent.txt", question)

        if data and "intent" in data:
            intent = data["intent"]
            self._log(f"  -> intent classificato: {intent}")
            return intent

        self._log("  [warn] classificazione fallita, fallback a 'unknown'")
        return "unknown"

    # ----- estrattori di parametri -----

    def _extract_city(self, question: str) -> str | None:
        """usa il llm per estrarre il nome della città dalla domanda."""
        self._log("\n[info] [step] estrazione città via llm")
        data = self._llm_extract_json("extract_city.txt", question)

        if data and data.get("city"):
            self._log(f"  -> città estratta: {data['city']}")
            return data["city"]

        # fallback: risposta grezza come nome della città
        self._log("  [warn] estrazione città fallita")
        return None

    def _extract_exchange_params(self, question: str) -> dict[str, str | None]:
        """usa il llm per estrarre le valute dalla domanda."""
        self._log("\n[info] [step] estrazione valute via llm")
        data = self._llm_extract_json("extract_exchange.txt", question)

        if data:
            from_c = data.get("from_currency")
            to_c = data.get("to_currency")
            self._log(f"  -> valute estratte: {from_c} -> {to_c}")
            return {"from_currency": from_c, "to_currency": to_c}

        self._log("  [warn] estrazione valute fallita")
        return {"from_currency": None, "to_currency": None}

    # ----- pipeline -----

    def _run_weather(self, question: str) -> list[dict[str, Any]]:
        """esegue il ramo weather della pipeline."""
        city = self._extract_city(question)
        if not city:
            return [{"error": "Non sono riuscito a identificare una città nella domanda."}]

        self._log(f"\n[info] [step] chiamata weather provider per '{city}'")
        result = self.weather.fetch({"city": city})

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
        else:
            self._log(f"  -> meteo recuperato: {result.get('condition')} {result.get('temperature_c')}°C")
        return [result]

    def _run_exchange(self, question: str) -> list[dict[str, Any]]:
        """esegue il ramo exchange_rate della pipeline."""
        params = self._extract_exchange_params(question)
        if not params.get("from_currency") or not params.get("to_currency"):
            return [{"error": "Non sono riuscito a identificare le valute nella domanda."}]

        self._log(f"\n[info] [step] chiamata exchange provider per {params['from_currency']} -> {params['to_currency']}")
        result = self.exchange.fetch(params)

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
        else:
            self._log(f"  -> tasso recuperato: {params['from_currency']}/{params['to_currency']} = {result.get('rates')}")
        return [result]

    def run(self, question: str) -> tuple[list[dict[str, Any]], str]:
        """esegue la pipeline: classifica intent -> estrai parametri -> chiama provider -> risultati.

        Returns:
            tupla (lista risultati, intent string).
        """
        intent = self._classify_intent(question)

        if intent == "weather":
            results = self._run_weather(question)
        elif intent == "exchange_rate":
            results = self._run_exchange(question)
        else:
            results = [{"error": f"Intent '{intent}' non supportato. Prova con domande su meteo o tassi di cambio."}]

        return results, intent
