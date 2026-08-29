"""
Test del cambio valuta senza rete: validazione di importo e data, e coerenza
fra tasso unitario e importo convertito.
"""

from datetime import date, timedelta

from conftest import RispostaFinta, SessionFinta
from providers.exchange_provider import ExchangeProvider

TASSO = {"amount": 1.0, "base": "USD", "date": "2026-08-21", "rates": {"EUR": 0.85477}}


def provider_con(*risposte):
    p = ExchangeProvider()
    p.session = SessionFinta(*risposte)
    return p


def test_converted_deriva_dal_tasso_unitario():
    """il valore convertito deve essere coerente col tasso restituito."""
    p = provider_con(RispostaFinta(TASSO))
    r = p.fetch({"from_currency": "USD", "to_currency": "EUR", "amount": 100})
    assert r["rates"] == 0.85477
    assert r["converted"] == round(100 * 0.85477, 2) == 85.48


def test_si_chiede_il_tasso_unitario_non_l_importo():
    """l'api arrotonda l'importo convertito, perdendo la precisione del tasso."""
    p = provider_con(RispostaFinta(TASSO))
    p.fetch({"from_currency": "USD", "to_currency": "EUR", "amount": 100})
    _, params = p.session.chiamate[0]
    assert "amount" not in params


def test_data_costruisce_l_url_del_fixing():
    p = provider_con(RispostaFinta({**TASSO, "date": "2020-01-02"}))
    p.fetch({"from_currency": "USD", "to_currency": "EUR", "date": "2020-01-02"})
    url, _ = p.session.chiamate[0]
    assert url.endswith("/2020-01-02")


def test_senza_data_si_usa_latest():
    p = provider_con(RispostaFinta(TASSO))
    p.fetch({"from_currency": "USD", "to_currency": "EUR"})
    url, _ = p.session.chiamate[0]
    assert url.endswith("/latest")


def test_giorno_diverso_dal_richiesto_viene_dichiarato():
    """senza fixing per la data chiesta si usa il precedente, dichiarandolo."""
    p = provider_con(RispostaFinta({**TASSO, "date": "2020-01-03"}))
    r = p.fetch({"from_currency": "USD", "to_currency": "EUR", "date": "2020-01-05"})
    assert r["date"] == "2020-01-03"
    assert r["requested_date"] == "2020-01-05"


def test_data_coincidente_non_aggiunge_rumore():
    p = provider_con(RispostaFinta({**TASSO, "date": "2020-01-02"}))
    r = p.fetch({"from_currency": "USD", "to_currency": "EUR", "date": "2020-01-02"})
    assert "requested_date" not in r


def test_data_futura_ricade_su_oggi():
    domani = (date.today() + timedelta(days=30)).isoformat()
    assert ExchangeProvider._parse_date(domani) == date.today()


def test_date_inutilizzabili():
    for cattiva in ["ieri", "", None, "2020-13-45", "1980-01-01", 42]:
        assert ExchangeProvider._parse_date(cattiva) is None


def test_importi_inutilizzabili_valgono_uno():
    for cattivo in ["tanti", None, -5, 0, [], {}]:
        assert ExchangeProvider._parse_amount(cattivo) == 1.0


def test_valuta_minuscola_viene_normalizzata():
    """frankfurter indicizza rates con codici maiuscoli."""
    p = provider_con(RispostaFinta(TASSO))
    r = p.fetch({"from_currency": "usd", "to_currency": "eur"})
    assert "error" not in r
    assert r["quote"] == "EUR"


def test_stessa_valuta_non_chiama_la_rete():
    p = provider_con()  # nessuna risposta preparata: una chiamata farebbe fallire
    r = p.fetch({"from_currency": "EUR", "to_currency": "EUR", "amount": 250})
    assert r["rates"] == 1.0
    assert r["converted"] == 250.0
    assert p.session.chiamate == []


def test_404_su_data_remota_da_errore_parlante():
    p = provider_con(RispostaFinta(None, status_code=404))
    r = p.fetch({"from_currency": "EUR", "to_currency": "USD", "date": "1999-01-05"})
    assert "1999-01-05" in r["error"]
