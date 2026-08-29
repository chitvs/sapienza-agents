import logging
import urllib.parse
import requests
from typing import Any
from configs.settings import settings

logger = logging.getLogger(__name__)


class CountryProvider:
    """provider informazioni sui paesi basato su countries.dev (gratuito, no API key)."""

    def __init__(self):
        self.session = requests.Session()

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Recupera le informazioni di un paese interrogando l'endpoint /name/{name} di countries.dev."""
        country = params.get("country", "").strip().strip('"').strip("'")
        if not country:
            return {"error": "Nessun paese specificato nella domanda."}

        url = f"{settings.countries_dev_base_url.rstrip('/')}/name/{urllib.parse.quote(country)}"

        try:
            res = self.session.get(url, timeout=10)

            if res.status_code == 404:
                return {"error": f"Paese '{country}' non trovato."}

            res.raise_for_status()
            data = res.json()

            if not isinstance(data, list) or len(data) == 0:
                return {"error": f"Paese '{country}' non trovato."}

            c = data[0]

            return {
                "provider": "countries.dev",
                "name": c.get("name", country),
                # countries.dev espone il solo nome nella lingua locale
                # ("Italia"), non quello ufficiale ("Repubblica Italiana")
                "native_name": c.get("nativeName", ""),
                "capital": c.get("capital"),
                "region": c.get("region", ""),
                "subregion": c.get("subregion", ""),
                "population": c.get("population", 0),
                "area_km2": c.get("area", 0),
                "languages": [lang.get("name", "") for lang in c.get("languages", []) if isinstance(lang, dict)],
                "currencies": c.get("currencies", []),
                "timezones": c.get("timezones", []),
                "borders": c.get("borders", []),
                "flag_emoji": c.get("flag", ""),
                "flag_png": c.get("flags", {}).get("png", "") if isinstance(c.get("flags"), dict) else "",
            }

        except Exception as err:
            logger.warning("fetch paese fallito per '%s': %s", country, err)
            return {"error": f"Errore nel recupero dei dati del paese: {err}"}
