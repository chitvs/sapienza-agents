import json
from datetime import date
import re
import logging
from typing import Any

import requests

from configs.settings import settings
from providers.weather_provider import WeatherProvider
from providers.exchange_provider import ExchangeProvider
from providers.country_provider import CountryProvider
from providers.worldtime_provider import WorldTimeProvider
import summaries
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

    def _llm_extract_json(self, prompt_file: str, question: str, **extra) -> dict | None:
        """helper generico: carica un prompt, lo invia al llm, parsa il json di risposta.

        Se il parse fallisce, attiva il corrector per riprovare con feedback.
        """
        template = self._load_prompt(prompt_file)
        prompt = template.format(question=question, **extra)
        raw = self._llm_generate(prompt)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            data = None

        # json.loads accetta anche array e scalari, su cui l'accesso per chiave
        # solleverebbe AttributeError: vale solo un oggetto
        if isinstance(data, dict):
            return data

        if data is not None:
            self._log(f"  [warn] json valido ma non è un oggetto ({type(data).__name__})")

        self._log("  [warn] risposta inutilizzabile, attivazione corrector...")
        corrected = self.corrector.extract_json_with_retry(
            llm_generate_fn=self._llm_generate,
            clean_json_fn=self._clean_json,
            original_prompt=prompt,
            failed_response=raw,
        )
        return corrected if isinstance(corrected, dict) else None

    # ----- classificatore di intent -----

    SUPPORTED_INTENTS = ("weather", "exchange_rate", "country_info", "time_info")

    def _classify_intent(self, question: str) -> tuple[str, list[str]]:
        """classifica la domanda e rileva gli eventuali temi secondari.

        Returns:
            (intent principale, altri intent citati nella domanda). La pipeline
            risponde solo al principale: restituire anche gli altri permette di
            dire quale parte della domanda è rimasta senza risposta.
        """
        self._log("\n[info] [step] classificazione intent via llm")
        data = self._llm_extract_json("classify_intent.txt", question)

        if data and "intent" in data:
            intent = data["intent"]
            altri = data.get("other_intents") or []
            if not isinstance(altri, list):
                altri = []
            # il modello può ripetere il principale o inventare etichette
            altri = [i for i in altri if i in self.SUPPORTED_INTENTS and i != intent]
            self._log(f"  -> intent classificato: {intent}" + (f" (ignorati: {altri})" if altri else ""))
            return intent, altri

        self._log("  [warn] classificazione fallita, fallback a 'unknown'")
        return "unknown", []

    # ----- estrattori di parametri -----

    def _extract_weather_params(self, question: str) -> dict[str, Any]:
        """usa il llm per estrarre città e giorno di riferimento dalla domanda."""
        self._log("\n[info] [step] estrazione città via llm")
        # senza la data corrente il modello non può tradurre "domani" in un numero
        data = self._llm_extract_json(
            "extract_city.txt", question, today=date.today().isoformat()
        )

        if data and data.get("city"):
            giorni = data.get("days_ahead")
            quando = "adesso" if giorni is None else f"+{giorni} giorni"
            self._log(f"  -> città estratta: {data['city']} ({quando})")
            return {"city": data["city"], "days_ahead": giorni}

        self._log("  [warn] estrazione città fallita")
        return {"city": None, "days_ahead": None}

    def _extract_exchange_params(self, question: str) -> dict[str, Any]:
        """usa il llm per estrarre valute, importo ed eventuale data dalla domanda."""
        self._log("\n[info] [step] estrazione valute via llm")
        # la data corrente ancora le espressioni relative come "l'anno scorso"
        data = self._llm_extract_json(
            "extract_exchange.txt", question, today=date.today().isoformat()
        )

        if data:
            from_c = data.get("from_currency")
            to_c = data.get("to_currency")
            amount = data.get("amount")
            when = data.get("date")
            self._log(f"  -> estratti: {amount or 1} {from_c} -> {to_c} (data: {when or 'oggi'})")
            return {
                "from_currency": from_c,
                "to_currency": to_c,
                "amount": amount,
                "date": when,
            }

        self._log("  [warn] estrazione valute fallita")
        return {"from_currency": None, "to_currency": None, "amount": None, "date": None}

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
        params = self._extract_weather_params(question)
        city = params.get("city")
        if not city:
            return [{"error": "Non sono riuscito a identificare una città nella domanda."}]

        self._log(f"\n[info] [step] chiamata weather provider per '{city}'")
        result = self.weather.fetch(params)

        if "error" in result:
            self._log(f"  [warn] errore provider: {result['error']}")
        else:
            if result.get("kind") == "forecast":
                self._log(f"  -> previsione {result.get('date')}: {result.get('condition')} "
                          f"{result.get('temperature_min_c')}-{result.get('temperature_max_c')}°C")
            else:
                self._log(f"  -> meteo attuale: {result.get('condition')} {result.get('temperature_c')}°C")
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
            self._log(f"  -> {result.get('amount')} {result.get('base')} = {result.get('converted')} {result.get('quote')} (tasso {result.get('rates')}, {result.get('date')})")
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

    def run(self, question: str) -> tuple[list[dict[str, Any]], str, bool, list[str]]:
        """esegue la pipeline: cache check -> classifica intent -> estrai parametri -> chiama provider.

        Returns:
            tupla (risultati, intent, servito dalla cache, intent ignorati).
        """
        # step 0: controlla la cache
        cached = self.cache.get(question)
        if cached:
            self._log("\n[info] [step] cache hit! risultati trovati in cache")
            return cached["results"], cached["intent"], True, cached.get("ignored", [])

        # step 1: classifica intent
        intent, ignorati = self._classify_intent(question)

        # step 2: esegui un ramo per ogni intent riconosciuto, entro il tetto
        # configurato: ogni intent in più costa una chiamata al llm e una all'api
        rami = {
            "weather": self._run_weather,
            "exchange_rate": self._run_exchange,
            "country_info": self._run_country,
            "time_info": self._run_worldtime,
        }
        da_servire = [intent] + ignorati[: max(0, settings.max_intents_per_question - 1)]

        results: list[dict[str, Any]] = []
        for corrente in da_servire:
            ramo = rami.get(corrente)
            if ramo is None:
                results.append({
                    "error": f"Intent '{corrente}' non supportato. Prova con domande su meteo, "
                             "tassi di cambio, informazioni sui paesi o orario locale."
                })
                continue

            parziali = ramo(question)
            for r in parziali:
                # ogni risultato dichiara da quale intent proviene: è ciò che
                # permette di renderlo con la card giusta quando ce n'è più d'uno
                r.setdefault("intent", corrente)
            # step 2b: sintesi in linguaggio naturale, usata dagli llm a valle
            results.extend(summaries.aggiungi(corrente, parziali))

        # gli intent serviti non sono più "ignorati"
        ignorati = [i for i in ignorati if i not in da_servire]

        # step 3: salva in cache solo se ogni risultato è valido, con la durata
        # più breve fra gli intent serviti: la risposta è unica e scade tutta
        # insieme, quindi vale il dato che invecchia prima
        if results and not any("error" in r for r in results):
            ttl = min(
                settings.cache_ttl_by_intent.get(i, settings.cache_ttl_default)
                for i in da_servire
            )
            self.cache.set(question, intent, results, ttl=ttl, ignored=ignorati)

        return results, intent, False, ignorati
