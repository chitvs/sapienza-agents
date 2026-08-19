import logging
import requests
from typing import Any
from configs.settings import settings

logger = logging.getLogger(__name__)


class WorldTimeProvider:
    """provider ora locale basato su world-time-api3 (RapidAPI, richiede api key).

    Flusso:
    1. geocoding della città via open-meteo (restituisce già il campo timezone IANA)
    2. chiamata a world-time-api3 /timezone/{tz} per l'ora corrente
    """

    def __init__(self):
        self.session = requests.Session()

    def _get_timezone(self, city: str) -> dict[str, str] | None:
        """converte il nome di una città nel suo timezone IANA tramite open-meteo geocoding.

        Riutilizza lo stesso endpoint già usato da WeatherProvider, che restituisce
        il campo 'timezone' nel formato 'Europe/Rome', 'Asia/Tokyo', ecc.

        Returns:
            dict con timezone IANA, nome località e codice paese ISO-2,
            oppure None se la località non è stata trovata.
        """
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        try:
            res = self.session.get(
                settings.open_meteo_geocoding_url, params=params, timeout=10
            )
            res.raise_for_status()
            data = res.json()
            if "results" in data and data["results"]:
                r = data["results"][0]
                tz = r.get("timezone")
                name = r.get("name", city)
                country = r.get("country", "")
                if tz:
                    return {
                        "timezone": tz,
                        "location": f"{name}, {country}" if country else name,
                        # ISO-3166 alpha-2 (es. "JP"): serve alla ui per la bandiera
                        "country_code": r.get("country_code", ""),
                    }
        except Exception as err:
            logger.warning("geocoding fallito per '%s': %s", city, err)
        return None

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """recupera l'ora locale per una città interrogando world-time-api3.

        Args:
            params: dizionario con chiave "city" (nome della città o regione).

        Returns:
            dizionario con i dati dell'ora corrente oppure con chiave "error".
        """
        city = params.get("city", "").strip()
        if not city:
            return {"error": "Nessuna città specificata nella domanda."}

        # step 1: ottieni il timezone IANA dalla città
        geo = self._get_timezone(city)
        if not geo:
            return {"error": f"Città o regione '{city}' non trovata."}
        timezone = geo["timezone"]
        location_name = geo["location"]

        # step 2: chiama world-time-api3 per l'ora corrente
        if not settings.timeapi_api_key:
            return {"error": "TIMEAPI_API_KEY non configurata: copia .env.example in .env e inserisci la chiave RapidAPI."}

        url = f"{settings.worldtime_base_url.rstrip('/')}/{timezone}"
        headers = {
            "x-rapidapi-key": settings.timeapi_api_key,
            "x-rapidapi-host": settings.worldtime_api_host,
        }
        try:
            res = self.session.get(url, headers=headers, timeout=10)

            if res.status_code == 404:
                return {"error": f"Timezone '{timezone}' non trovato sul provider."}
            if res.status_code in (401, 403):
                # 401 = chiave assente/errata, 403 = chiave valida ma non iscritta all'API
                # (capita anche se la chiave contiene virgolette o spazi di troppo)
                logger.error("autenticazione RapidAPI fallita (%s): %s", res.status_code, res.text[:200])
                return {"error": "Chiave API per il servizio orario non valida o non abilitata (TIMEAPI_API_KEY)."}
            if res.status_code == 429:
                return {"error": "Limite di richieste del servizio orario superato, riprova più tardi."}

            res.raise_for_status()
            data = res.json()

            # il campo datetime è in formato ISO 8601: '2026-08-14T17:30:45.123456+02:00'
            dt_str = data.get("datetime", "")
            time_str = dt_str[11:19] if len(dt_str) >= 19 else ""  # HH:MM:SS
            date_str = dt_str[:10] if len(dt_str) >= 10 else ""    # YYYY-MM-DD

            return {
                "provider": "timeapi",
                "city": location_name,
                "country_code": geo["country_code"],
                "timezone": data.get("timezone", timezone),
                "datetime": dt_str,
                "time": time_str,
                "date": date_str,
                "utc_offset": data.get("utc_offset", ""),
                "abbreviation": data.get("abbreviation", ""),
                "dst": data.get("dst", False),
                "day_of_week": data.get("day_of_week"),
                "week_number": data.get("week_number"),
            }

        except Exception as err:
            logger.warning("fetch worldtime fallito per timezone '%s': %s", timezone, err)
            return {"error": f"Errore nel recupero dell'ora per '{city}': {err}"}
