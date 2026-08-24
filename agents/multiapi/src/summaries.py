"""
Sintesi in linguaggio naturale dei risultati dei provider.

Orchestratore e planner passano i risultati a un llm come evidenze: una riga
in linguaggio naturale è più difficile da fraintendere di un dizionario di
campi tecnici, e occupa meno contesto.
"""

from typing import Any

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def data_estesa(iso: str) -> str:
    """'2026-08-25' -> '25 agosto 2026'; restituisce l'originale se non riconosciuta."""
    if not isinstance(iso, str) or len(iso) < 10:
        return iso or ""
    try:
        anno, mese, giorno = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
        return f"{giorno} {MESI[mese - 1]} {anno}"
    except (ValueError, IndexError):
        return iso


def _migliaia(n: Any) -> str:
    """125836021 -> '125.836.021'.

    Il formato ':n' dipende dal locale del processo, che nel container non è
    italiano: il separatore si mette a mano.
    """
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _luogo(r: dict[str, Any]) -> str:
    citta = r.get("city") or ""
    paese = r.get("country") or ""
    return f"{citta} ({paese})" if paese and paese not in citta else citta


def meteo(r: dict[str, Any]) -> str:
    if r.get("kind") == "forecast":
        quando = {0: "oggi", 1: "domani", 2: "dopodomani"}.get(
            r.get("days_ahead"), f"il {data_estesa(r.get('date', ''))}"
        )
        pezzi = [f"Previsione meteo per {_luogo(r)} {quando} ({data_estesa(r.get('date', ''))}): {r.get('condition', '').lower()}"]
        if r.get("temperature_min_c") is not None and r.get("temperature_max_c") is not None:
            pezzi.append(f"temperatura fra {r['temperature_min_c']}°C e {r['temperature_max_c']}°C")
        if r.get("precipitation_probability_percent") is not None:
            pezzi.append(f"probabilità di pioggia {r['precipitation_probability_percent']}%")
        if r.get("sunrise") and r.get("sunset"):
            pezzi.append(f"alba alle {r['sunrise']}, tramonto alle {r['sunset']}")
        return ", ".join(pezzi) + "."

    pezzi = [f"Meteo attuale a {_luogo(r)}: {str(r.get('condition', '')).lower()}"]
    if r.get("temperature_c") is not None:
        pezzi.append(f"{r['temperature_c']}°C")
    if r.get("apparent_temperature_c") is not None:
        pezzi.append(f"percepiti {r['apparent_temperature_c']}°C")
    if r.get("humidity_percent") is not None:
        pezzi.append(f"umidità {r['humidity_percent']}%")
    if r.get("wind_speed_kmh") is not None:
        pezzi.append(f"vento {r['wind_speed_kmh']} km/h")
    return ", ".join(pezzi) + "."


def cambio(r: dict[str, Any]) -> str:
    base, quote = r.get("base", ""), r.get("quote", "")
    quando = f"al {data_estesa(r['date'])}" if r.get("date") else ""
    if r.get("amount") and r["amount"] != 1:
        testo = f"{r['amount']} {base} equivalgono a {r.get('converted')} {quote} {quando}"
    else:
        testo = f"1 {base} vale {r.get('rates')} {quote} {quando}"
    if r.get("requested_date"):
        testo += f" (per il {data_estesa(r['requested_date'])} non esiste un cambio ufficiale: usato il giorno lavorativo precedente)"
    return testo.strip() + "."


def paese(r: dict[str, Any]) -> str:
    pezzi = [f"{r.get('name', '')}"]
    if r.get("capital"):
        pezzi.append(f"capitale {r['capital']}")
    if r.get("population"):
        pezzi.append(f"{_migliaia(r['population'])} abitanti")
    if r.get("area_km2"):
        pezzi.append(f"superficie {_migliaia(r['area_km2'])} km²")
    if r.get("languages"):
        pezzi.append("lingue: " + ", ".join(r["languages"]))
    valute = [c.get("code") for c in r.get("currencies", []) if isinstance(c, dict) and c.get("code")]
    if valute:
        pezzi.append("valuta: " + ", ".join(valute))
    return ", ".join(p for p in pezzi if p) + "."


def ora(r: dict[str, Any]) -> str:
    testo = f"A {r.get('city', '')} sono le {r.get('time', '')} del {data_estesa(r.get('date', ''))}"
    if r.get("timezone"):
        testo += f" (fuso {r['timezone']}"
        testo += f", UTC{r['utc_offset']})" if r.get("utc_offset") else ")"
    return testo + "."


PER_INTENT = {
    "weather": meteo,
    "exchange_rate": cambio,
    "country_info": paese,
    "time_info": ora,
}


def aggiungi(intent: str, risultati: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """aggiunge il campo "summary" ai risultati riusciti dell'intent indicato."""
    funzione = PER_INTENT.get(intent)
    if not funzione:
        return risultati
    for r in risultati:
        if isinstance(r, dict) and "error" not in r and "summary" not in r:
            try:
                r["summary"] = funzione(r)
            except Exception:
                # la sintesi è accessoria: non deve invalidare dati validi
                pass
    return risultati
