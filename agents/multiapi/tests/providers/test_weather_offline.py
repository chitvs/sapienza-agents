"""
Test del weather provider senza rete: parsing delle risposte e scelta fra
condizioni correnti e previsione.
"""

from conftest import RispostaFinta, SessionFinta
from providers.weather_provider import WeatherProvider

GEOCODING = {
    "results": [{
        "name": "Milano", "country": "Italia", "country_code": "IT",
        "latitude": 45.46, "longitude": 9.19, "timezone": "Europe/Rome",
    }]
}

CORRENTE = {
    "current": {
        "temperature_2m": 29.7, "relative_humidity_2m": 55,
        "apparent_temperature": 31.2, "weather_code": 3, "wind_speed_10m": 8.1,
    }
}

PREVISIONE = {
    "daily": {
        "time": ["2026-08-24", "2026-08-25"],
        "weather_code": [3, 80],
        "temperature_2m_max": [29.9, 28.0],
        "temperature_2m_min": [19.5, 21.1],
        "precipitation_probability_max": [10, 88],
        "sunrise": ["2026-08-24T06:35", "2026-08-25T06:36"],
        "sunset": ["2026-08-24T20:16", "2026-08-25T20:14"],
    }
}


def provider_con(*risposte):
    p = WeatherProvider()
    p.session = SessionFinta(*risposte)
    return p


def test_senza_days_ahead_restituisce_il_presente():
    p = provider_con(RispostaFinta(GEOCODING), RispostaFinta(CORRENTE))
    r = p.fetch({"city": "Milano"})
    assert r["kind"] == "current"
    assert r["temperature_c"] == 29.7
    assert r["condition"] == "Coperto"
    assert "temperature_max_c" not in r


def test_days_ahead_restituisce_la_previsione_del_giorno_giusto():
    p = provider_con(RispostaFinta(GEOCODING), RispostaFinta(PREVISIONE))
    r = p.fetch({"city": "Milano", "days_ahead": 1})
    assert r["kind"] == "forecast"
    assert r["date"] == "2026-08-25"
    assert r["temperature_min_c"] == 21.1
    assert r["temperature_max_c"] == 28.0
    assert r["precipitation_probability_percent"] == 88
    assert r["condition"] == "Rovescio leggero"
    # dalle stringhe iso deve restare solo l'ora
    assert r["sunrise"] == "06:36"
    assert r["sunset"] == "20:14"


def test_chiede_i_giorni_necessari_e_non_di_piu():
    p = provider_con(RispostaFinta(GEOCODING), RispostaFinta(PREVISIONE))
    p.fetch({"city": "Milano", "days_ahead": 1})
    _, params = p.session.chiamate[1]
    assert params["forecast_days"] == 2, "servono i giorni fino a quello richiesto, incluso"


def test_days_ahead_oltre_il_massimo_viene_limitato():
    assert WeatherProvider._parse_days_ahead(99) == WeatherProvider.MAX_DAYS_AHEAD


def test_days_ahead_non_valido_ricade_sul_presente():
    for cattivo in ["domani", None, -3, {}, True]:
        assert WeatherProvider._parse_days_ahead(cattivo) is None


def test_previsione_piu_corta_del_richiesto_da_errore():
    """con meno giorni del richiesto non si deve leggere fuori dalla lista."""
    corta = {"daily": {"time": ["2026-08-24"], "weather_code": [3],
                       "temperature_2m_max": [29.9], "temperature_2m_min": [19.5],
                       "precipitation_probability_max": [10],
                       "sunrise": ["2026-08-24T06:35"], "sunset": ["2026-08-24T20:16"]}}
    p = provider_con(RispostaFinta(GEOCODING), RispostaFinta(corta))
    r = p.fetch({"city": "Milano", "days_ahead": 3})
    assert "error" in r


def test_citta_non_trovata_non_chiama_il_meteo():
    p = provider_con(RispostaFinta({"results": []}))
    r = p.fetch({"city": "Xyz"})
    assert "error" in r
    assert len(p.session.chiamate) == 1, "senza coordinate non ha senso interrogare il meteo"


def test_codice_wmo_sconosciuto_non_rompe():
    strano = {"current": {"temperature_2m": 20.0, "weather_code": 999}}
    p = provider_con(RispostaFinta(GEOCODING), RispostaFinta(strano))
    r = p.fetch({"city": "Milano"})
    assert r["condition"] == "Sconosciuto"
