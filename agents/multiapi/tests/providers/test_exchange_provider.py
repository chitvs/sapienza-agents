from providers.exchange_provider import ExchangeProvider


def test_fetch_usd_to_eur():
    """il provider deve restituire un tasso valido per USD -> EUR."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "USD", "to_currency": "EUR"})
    assert "error" not in result
    assert result["provider"] == "frankfurter"
    assert "rates" in result
    assert isinstance(result["rates"], (int, float))
    assert result["rates"] > 0


def test_fetch_eur_to_gbp():
    """il provider deve funzionare per qualsiasi coppia di valute valide."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "EUR", "to_currency": "GBP"})
    assert "error" not in result
    assert result["base"] == "EUR"


def test_fetch_same_currency():
    """il provider deve gestire il caso valuta uguale senza chiamare l'API."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "EUR", "to_currency": "EUR"})
    assert "error" not in result
    assert result["rates"] == 1.0


def test_fetch_missing_from_currency():
    """il provider deve restituire un errore se manca from_currency."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "", "to_currency": "EUR"})
    assert "error" in result


def test_fetch_missing_to_currency():
    """il provider deve restituire un errore se manca to_currency."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "USD", "to_currency": ""})
    assert "error" in result


def test_fetch_invalid_currency():
    """il provider deve restituire un errore per valute non valide."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "PIZZA", "to_currency": "EUR"})
    assert "error" in result
