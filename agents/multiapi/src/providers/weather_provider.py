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
    """provider meteo basato su open-meteo (nessuna api key necessaria)."""

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

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Chiama l'API di Open-Meteo per il meteo attuale e restituisce un dizionario pulito.
        Args:
            params: dizionario con chiave "city" (nome della città).

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
