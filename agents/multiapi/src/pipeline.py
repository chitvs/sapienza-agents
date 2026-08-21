import json
import re
import logging
from typing import Any

import requests

from configs.settings import settings
from providers.weather_provider import WeatherProvider
from providers.exchange_provider import ExchangeProvider
from providers.country_provider import CountryProvider
from providers.worldtime_provider import WorldTimeProvider
from cache.response_cache import ResponseCache
from correctors.llm_response_corrector import LlmResponseCorrector

logger = logging.getLogger("multiapi_pipeline")


class MultiApiPipeline:
    """pipeline dell'agente multiapi: classifica l'intent, estrae i parametri e chiama il provider giusto.

    Integra:
    - cache in-memory per evitare chiamate duplicate
    - corrector per riprovare quando il LLM non restituisce JSON valido
    """

    def __init__(self, verbose: bool = False):
        self.weather = WeatherProvider()
        self.exchange = ExchangeProvider()
        self.country = CountryProvider()
        self.worldtime = WorldTimeProvider()
        self.cache = ResponseCache(
            capacity=settings.cache_capacity,
            default_ttl=settings.cache_ttl_default,
        )
        self.corrector = LlmResponseCorrector(max_retries=settings.max_llm_retries)
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
        """helper generico: carica un prompt, lo invia al llm, parsa il json di risposta.

        Se il parse fallisce, attiva il corrector per riprovare con feedback.
        """
        template = self._load_prompt(prompt_file)
        prompt = template.format(question=question)
        raw = self._llm_generate(prompt)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log("  [warn] json non valido, attivazione corrector...")
            return self.corrector.extract_json_with_retry(
                llm_generate_fn=self._llm_generate,
                clean_json_fn=self._clean_json,
                original_prompt=prompt,
                failed_response=raw,
            )

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

    def _extract_country(self, question: str) -> str | None:
        """usa il llm per estrarre il nome del paese dalla domanda."""
        self._log("\n[info] [step] estrazione paese via llm")
        data = self._llm_extract_json("extract_country.txt", question)

        if data and data.get("country"):
            self._log(f"  -> paese estratto: {data['country']}")
            return data["country"]

        self._log("  [warn] estrazione paese fallita")
        return None

    def _extract_timezone_city(self, question: str) -> str | None:
        """usa il llm per estrarre il nome della città/regione da una domanda sull'ora."""
        self._log("\n[info] [step] estrazione città (timezone) via llm")
        data = self._llm_extract_json("extract_timezone.txt", question)

        if data and data.get("city"):
            self._log(f"  -> città estratta: {data['city']}")
            return data["city"]

        self._log("  [warn] estrazione città (timezone) fallita")
        return None

    # ----- rami della pipeline -----

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

    def _run_country(self, question: str) -> list[dict[str, Any]]:
        """esegue il ramo country_info della pipeline."""
        country = self._extract_country(question)
        if not country:
            return [{"error": "Non sono riuscito a identificare un paese nella domanda."}]

        self._log(f"\n[info] [step] chiamata country provider per '{country}'")
        result = self.country.fetch({"country": country})

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
        else:
            self._log(f"  -> info recuperate: {result.get('name')} (capitale: {result.get('capital')})")
        return [result]

    def _run_worldtime(self, question: str) -> list[dict[str, Any]]:
        """esegue il ramo time_info della pipeline."""
        city = self._extract_timezone_city(question)
        if not city:
            return [{"error": "Non sono riuscito a identificare una città nella domanda."}]

        self._log(f"\n[info] [step] chiamata worldtime provider per '{city}'")
        result = self.worldtime.fetch({"city": city})

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
        else:
            self._log(f"  -> ora recuperata: {result.get('city')} {result.get('time')} ({result.get('timezone')})")
        return [result]

    # ----- pipeline principale -----

    def run(self, question: str) -> tuple[list[dict[str, Any]], str, bool]:
        """esegue la pipeline: cache check -> classifica intent -> estrai parametri -> chiama provider.

        Returns:
            tupla (lista risultati, intent string, risposta servita dalla cache).
        """
        # step 0: controlla la cache
        cached = self.cache.get(question)
        if cached:
            self._log("\n[info] [step] cache hit! risultati trovati in cache")
            return cached["results"], cached["intent"], True

        # step 1: classifica intent
        intent = self._classify_intent(question)

        # step 2: esegui il ramo appropriato
        if intent == "weather":
            results = self._run_weather(question)
        elif intent == "exchange_rate":
            results = self._run_exchange(question)
        elif intent == "country_info":
            results = self._run_country(question)
        elif intent == "time_info":
            results = self._run_worldtime(question)
        else:
            results = [{"error": f"Intent '{intent}' non supportato. Prova con domande su meteo, tassi di cambio, informazioni sui paesi o orario locale."}]

        # step 3: salva in cache (solo se non c'è errore), con la durata
        # prevista per questo intent; un ttl di 0 significa non memorizzare
        if results and "error" not in results[0]:
            ttl = settings.cache_ttl_by_intent.get(intent, settings.cache_ttl_default)
            self.cache.set(question, intent, results, ttl=ttl)

        return results, intent, False
