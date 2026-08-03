import json
import re
import logging
from typing import Any
from pathlib import Path

import requests

from configs.settings import settings
from providers.weather_provider import WeatherProvider

logger = logging.getLogger("multiapi_pipeline")


class MultiApiPipeline:
    """pipeline minimale dell'agente multiapi: estrae la città via llm e interroga il meteo."""

    def __init__(self, verbose: bool = False):
        self.weather = WeatherProvider()
        self.verbose = verbose
        self._prompt_template: str | None = None

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
            "stream": False, #aspetta la risposta completa e non stampa token per token
            "options": {"temperature": temperature}, #temperatura llm 0 per avere risposte meno creative
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

    def _load_prompt(self) -> str:
        """carica il template del prompt per l'estrazione della città (lazy)."""
        if self._prompt_template is None:
            path = settings.prompts_dir / "extract_city.txt"
            self._prompt_template = path.read_text(encoding="utf-8")
        return self._prompt_template

    # ----- pipeline -----

    def _extract_city(self, question: str) -> str | None:
        """usa il llm per estrarre il nome della città dalla domanda."""
        self._log("\n[info] [step] estrazione città via llm")
        template = self._load_prompt()
        prompt = template.format(question=question)
        raw = self._llm_generate(prompt)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            data = json.loads(cleaned)
            city = data.get("city")
            if city:
                self._log(f"  -> città estratta: {city}")
            return city
        except (json.JSONDecodeError, AttributeError):
            # fallback: usa la risposta grezza come nome della città
            fallback = cleaned.strip().strip('"').strip("'")
            if fallback:
                self._log(f"  -> fallback città (raw): {fallback}")
                return fallback
            return None

    def run(self, question: str) -> tuple[list[dict[str, Any]], str]:
        """esegue la pipeline: estrazione città -> chiamata meteo -> risultati.

        Returns:
            tupla (lista risultati, intent string).
        """
        city = self._extract_city(question)

        if not city:
            return (
                [{"error": "Non sono riuscito a identificare una città nella domanda."}],
                "weather",
            )

        self._log(f"\n[info] [step] chiamata weather provider per '{city}'")
        result = self.weather.fetch({"city": city})

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
            return [result], "weather"

        self._log(f"  -> meteo recuperato: {result.get('condition')} {result.get('temperature_c')}°C")
        return [result], "weather"
