"""
Test delle sintesi in linguaggio naturale. Nessuna rete: sono pura formattazione.
"""

import summaries


def test_previsione_dice_il_giorno_e_i_valori():
    testo = summaries.meteo({
        "kind": "forecast", "city": "Milano", "country": "Italia", "days_ahead": 1,
        "date": "2026-08-25", "condition": "Rovescio leggero",
        "temperature_min_c": 21.1, "temperature_max_c": 28.0,
        "precipitation_probability_percent": 88, "sunrise": "06:36", "sunset": "20:14",
    })
    assert "Previsione" in testo
    assert "domani" in testo
    assert "25 agosto 2026" in testo
    assert "88%" in testo


def test_meteo_attuale_non_si_confonde_con_una_previsione():
    testo = summaries.meteo({
        "kind": "current", "city": "Milano", "country": "Italia",
        "condition": "Coperto", "temperature_c": 29.7,
    })
    assert "attuale" in testo
    assert "Previsione" not in testo


def test_previsione_oltre_dopodomani_usa_la_data():
    testo = summaries.meteo({
        "kind": "forecast", "city": "Roma", "days_ahead": 4,
        "date": "2026-08-28", "condition": "Sereno",
    })
    assert "28 agosto 2026" in testo


def test_campi_mancanti_non_rompono():
    """i provider possono restituire None per alcuni campi."""
    testo = summaries.meteo({"kind": "current", "city": "Roma", "condition": "Sereno"})
    assert testo.endswith(".")
    assert "None" not in testo


def test_cambio_con_importo():
    testo = summaries.cambio({
        "amount": 100.0, "base": "USD", "quote": "EUR",
        "rates": 0.8573, "converted": 85.73, "date": "2026-08-24",
    })
    assert "100.0 USD" in testo and "85.73 EUR" in testo


def test_cambio_senza_importo_parla_di_tasso():
    testo = summaries.cambio({"amount": 1.0, "base": "USD", "quote": "EUR", "rates": 0.8573, "date": "2026-08-24"})
    assert "1 USD vale" in testo


def test_cambio_spiega_la_data_spostata():
    testo = summaries.cambio({
        "amount": 1.0, "base": "USD", "quote": "EUR", "rates": 0.89,
        "date": "2020-01-03", "requested_date": "2020-01-05",
    })
    assert "5 gennaio 2020" in testo and "precedente" in testo


def test_paese_formatta_i_grandi_numeri():
    testo = summaries.paese({
        "name": "Japan", "capital": "Tokyo", "population": 125836021,
        "area_km2": 377930, "languages": ["Japanese"], "currencies": [{"code": "JPY"}],
    })
    assert "125.836.021 abitanti" in testo
    assert "377.930 km²" in testo


def test_ora_include_fuso_e_offset():
    testo = summaries.ora({
        "city": "Tokyo, Japan", "time": "01:01:00", "date": "2026-08-25",
        "timezone": "Asia/Tokyo", "utc_offset": "+09:00",
    })
    assert "01:01:00" in testo and "Asia/Tokyo" in testo and "UTC+09:00" in testo


def test_data_estesa_su_valori_strani():
    assert summaries.data_estesa("") == ""
    assert summaries.data_estesa(None) == ""
    assert summaries.data_estesa("non-una-data") == "non-una-data"
    assert summaries.data_estesa("2026-13-99") == "2026-13-99"


def test_migliaia_su_valori_non_numerici():
    assert summaries._migliaia("boh") == "boh"
    assert summaries._migliaia(None) == "None"


def test_aggiungi_salta_i_risultati_in_errore():
    risultati = [{"error": "città non trovata"}]
    assert "summary" not in summaries.aggiungi("weather", risultati)[0]


def test_aggiungi_ignora_intent_sconosciuti():
    risultati = [{"qualcosa": 1}]
    assert summaries.aggiungi("unknown", risultati) == [{"qualcosa": 1}]


def test_aggiungi_non_sovrascrive_una_sintesi_esistente():
    risultati = [{"kind": "current", "city": "Roma", "summary": "già scritta"}]
    assert summaries.aggiungi("weather", risultati)[0]["summary"] == "già scritta"


def test_aggiungi_non_propaga_eccezioni():
    """una sintesi che fallisce non invalida il risultato."""
    risultati = [{"kind": "forecast", "days_ahead": object()}]
    esito = summaries.aggiungi("weather", risultati)
    assert esito[0] is risultati[0]
