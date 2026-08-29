"""
Sonde dei servizi esterni condivise dai test dell'agente multiapi.

I test di unità usano risposte finte e non toccano la rete; quelli di
integrazione interrogano le api esterne e Ollama, e vengono saltati quando il
servizio non è raggiungibile. Le sonde sono in cache: una verifica per run.
"""

from functools import lru_cache

import pytest
import requests

from configs.settings import settings


@lru_cache(maxsize=1)
def is_ollama_running() -> bool:
    try:
        return requests.get(settings.ollama_host, timeout=1).status_code == 200
    except Exception:
        return False


@lru_cache(maxsize=1)
def is_open_meteo_reachable() -> bool:
    try:
        return requests.head(settings.open_meteo_forecast_url, timeout=3).status_code < 500
    except Exception:
        return False


@lru_cache(maxsize=1)
def is_frankfurter_reachable() -> bool:
    try:
        return requests.head(settings.frankfurter_base_url, timeout=3).status_code < 500
    except Exception:
        return False


@lru_cache(maxsize=1)
def is_countries_dev_reachable() -> bool:
    try:
        return requests.head(settings.countries_dev_base_url, timeout=3).status_code < 500
    except Exception:
        return False


@lru_cache(maxsize=1)
def is_worldtime_reachable() -> bool:
    """il servizio orario richiede una chiave: senza, i test si saltano."""
    if not settings.timeapi_api_key:
        return False
    try:
        res = requests.get(
            f"{settings.worldtime_base_url.rstrip('/')}/Europe/Rome",
            headers={
                "x-rapidapi-key": settings.timeapi_api_key,
                "x-rapidapi-host": settings.worldtime_api_host,
            },
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


# scorciatoie da usare come decoratori nei test di integrazione
richiede_ollama = pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
richiede_open_meteo = pytest.mark.skipif(not is_open_meteo_reachable(), reason="open-meteo non raggiungibile")
richiede_frankfurter = pytest.mark.skipif(not is_frankfurter_reachable(), reason="frankfurter non raggiungibile")
richiede_countries_dev = pytest.mark.skipif(not is_countries_dev_reachable(), reason="countries.dev non raggiungibile")
richiede_worldtime = pytest.mark.skipif(
    not is_worldtime_reachable(),
    reason="servizio orario non raggiungibile o TIMEAPI_API_KEY assente",
)


class RispostaFinta:
    """sostituto minimo di requests.Response per i test senza rete."""

    def __init__(self, json_data=None, status_code: int = 200, text: str = ""):
        self._json = json_data
        self.status_code = status_code
        self.text = text or ""

    def json(self):
        if self._json is None:
            raise ValueError("nessun corpo json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")


class SessionFinta:
    """Session che restituisce risposte preconfezionate e registra le chiamate.

    Le risposte si indicano nell'ordine in cui verranno consumate: i provider
    ne fanno più d'una in sequenza (geocoding, poi il dato).
    """

    def __init__(self, *risposte):
        self._risposte = list(risposte)
        self.chiamate: list[tuple[str, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.chiamate.append((url, params or {}))
        if not self._risposte:
            raise AssertionError(f"chiamata non prevista a {url}")
        return self._risposte.pop(0)
