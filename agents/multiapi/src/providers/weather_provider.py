import logging
import requests
from typing import Any
from configs.settings import settings

logger = logging.getLogger(__name__)

# Open-Meteo restituisce le condizioni meteo come numeri (codici WMO standard). Questa mappa li converte in testo leggibile.
WMO_CODES: dict[int, str] = {
    0: "Cielo sereno",
    1: "Prevalentemente sereno",
    2: "Parzialmente nuvoloso",
    3: "Coperto",
    45: "Nebbia",
    48: "Nebbia con brina",
    51: "Pioviggine leggera",
    53: "Pioviggine moderata",
    55: "Pioviggine intensa",
    56: "Pioviggine gelata leggera",
    57: "Pioviggine gelata intensa",
    61: "Pioggia leggera",
    63: "Pioggia moderata",
    65: "Pioggia intensa",
    66: "Pioggia gelata leggera",
    67: "Pioggia gelata intensa",
    71: "Neve leggera",
    73: "Neve moderata",
    75: "Neve intensa",
    77: "Granuli di neve",
    80: "Rovescio leggero",
    81: "Rovescio moderato",
    82: "Rovescio violento",
    85: "Rovescio di neve leggero",
    86: "Rovescio di neve intenso",
    95: "Temporale",
    96: "Temporale con grandine leggera",
    99: "Temporale con grandine forte",
}


class WeatherProvider:
    """provider meteo basato su open-meteo (nessuna api key necessaria).

    Due modalità, scelte dal parametro "days_ahead":
    - assente: condizioni correnti;
    - 0, 1, 2...: previsione del giorno indicato (0 = oggi, 1 = domani).

    Distinguerle è necessario: rispondere "pioverà domani?" con il meteo di
    adesso è una risposta sbagliata che sembra giusta.
    """

    # open-meteo copre 16 giorni, ma oltre la settimana l'attendibilità cala
    MAX_DAYS_AHEAD = 6

    def __init__(self):
        self.session = requests.Session()
        """Uso una sessione HTTP persistente. 
        Questo riutilizza la connessione TCP tra chiamate successive, 
        rendendole più veloci rispetto a fare requests.get() ogni volta."""

    def _geocode(self, city: str) -> dict[str, Any] | None:
        """converte il nome di una città in coordinate lat/lon tramite open-meteo geocoding."""
        params = {"name": city, "count": 1, "language": "it", "format": "json"}
        try:
            res = self.session.get(
                settings.open_meteo_geocoding_url, params=params, timeout=10
            )
            res.raise_for_status()
            data = res.json()
            if "results" in data and data["results"]:
                r = data["results"][0]
                return {
                    "name": r.get("name", city),
                    "country": r.get("country", ""),
                    # ISO-3166 alpha-2 (es. "IT"): serve alla ui per la bandiera
                    "country_code": r.get("country_code", ""),
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                }
        except Exception as err:
            logger.warning("geocoding fallito per '%s': %s", city, err)
        return None

    @classmethod
    def _parse_days_ahead(cls, value: Any) -> int | None:
        """numero di giorni nel futuro richiesti; None se la domanda è sul presente."""
        if value is None or isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            logger.warning("days_ahead non valido ignorato: %r", value)
            return None
        if days < 0:
            return None
        return min(days, cls.MAX_DAYS_AHEAD)

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Chiama Open-Meteo e restituisce un dizionario pulito.

        Args:
            params: "city" (nome della città) e, opzionale, "days_ahead"
                (0 = oggi, 1 = domani...). Assente significa "adesso".

        Returns:
            dizionario con i dati meteo oppure con chiave "error".
        """
        city = params.get("city", "")
        if not city:
            return {"error": "Nessuna città specificata nella domanda."}

        # geocoding: nome città -> coordinate
        location = self._geocode(city)
        if not location:
            return {"error": f"Città '{city}' non trovata."}

        days_ahead = self._parse_days_ahead(params.get("days_ahead"))
        if days_ahead is not None:
            return self._fetch_forecast(location, days_ahead)

        # chiamata api meteo attuale
        weather_params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "weather_code",
                "wind_speed_10m",
            ]),
            "timezone": "auto",
        }
        try:
            res = self.session.get(
                settings.open_meteo_forecast_url, params=weather_params, timeout=10
            )
            res.raise_for_status()
            data = res.json()
            current = data.get("current", {})

            weather_code = current.get("weather_code", -1)
            condition = WMO_CODES.get(weather_code, "Sconosciuto")

            return {
                "provider": "open-meteo",
                "kind": "current",
                "city": location["name"],
                "country": location["country"],
                "country_code": location["country_code"],
                "temperature_c": current.get("temperature_2m"),
                "apparent_temperature_c": current.get("apparent_temperature"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "condition": condition,
                "weather_code": weather_code,
            }
        except Exception as err:
            logger.warning("fetch meteo fallito: %s", err)
            return {"error": f"Errore nel recupero dei dati meteo: {err}"}

    def _fetch_forecast(self, location: dict[str, Any], days_ahead: int) -> dict[str, Any]:
        """previsione giornaliera per il giorno richiesto.

        Args:
            location: esito del geocoding.
            days_ahead: 0 = oggi, 1 = domani, ... (già validato).
        """
        forecast_params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "sunrise",
                "sunset",
            ]),
            # si chiedono i giorni fino a quello richiesto, incluso
            "forecast_days": days_ahead + 1,
            "timezone": "auto",
        }
        try:
            res = self.session.get(
                settings.open_meteo_forecast_url, params=forecast_params, timeout=10
            )
            res.raise_for_status()
            daily = res.json().get("daily", {})

            giorni = daily.get("time") or []
            if len(giorni) <= days_ahead:
                return {"error": f"Previsione non disponibile per {location['name']} fra {days_ahead} giorni."}

            def valore(chiave):
                serie = daily.get(chiave) or []
                return serie[days_ahead] if len(serie) > days_ahead else None

            weather_code = valore("weather_code")
            sunrise = valore("sunrise") or ""
            sunset = valore("sunset") or ""

            return {
                "provider": "open-meteo",
                "kind": "forecast",
                "city": location["name"],
                "country": location["country"],
                "country_code": location["country_code"],
                "days_ahead": days_ahead,
                "date": giorni[days_ahead],
                "temperature_min_c": valore("temperature_2m_min"),
                "temperature_max_c": valore("temperature_2m_max"),
                "precipitation_probability_percent": valore("precipitation_probability_max"),
                "condition": WMO_CODES.get(weather_code, "Sconosciuto"),
                "weather_code": weather_code if weather_code is not None else -1,
                # le stringhe arrivano come '2026-08-23T06:14': serve solo l'ora
                "sunrise": sunrise[11:16],
                "sunset": sunset[11:16],
            }
        except Exception as err:
            logger.warning("fetch previsioni fallito: %s", err)
            return {"error": f"Errore nel recupero delle previsioni: {err}"}
