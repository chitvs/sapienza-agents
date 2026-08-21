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


def test_converte_un_importo():
    """con un importo, il provider deve restituire anche la conversione."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "USD", "to_currency": "EUR", "amount": 100})
    assert "error" not in result
    assert result["amount"] == 100
    # converted deve essere coerente col tasso unitario, non un numero scollegato
    assert result["converted"] == round(100 * result["rates"], 2)
    assert result["converted"] > result["rates"]


def test_senza_importo_vale_uno():
    """senza importo la conversione coincide col tasso."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "USD", "to_currency": "EUR"})
    assert result["amount"] == 1.0
    assert result["converted"] == round(result["rates"], 2)


def test_importo_non_valido_viene_ignorato():
    """un importo assurdo estratto dal llm non deve rompere la richiesta."""
    provider = ExchangeProvider()
    for cattivo in ["tanti", None, -5, 0]:
        result = provider.fetch({"from_currency": "USD", "to_currency": "EUR", "amount": cattivo})
        assert "error" not in result
        assert result["amount"] == 1.0


def test_tasso_storico():
    """con una data passata deve tornare il fixing di quel giorno."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "USD", "to_currency": "EUR", "date": "2020-01-02"})
    assert "error" not in result
    assert result["date"] == "2020-01-02"
    assert result["rates"] == 0.89342  # valore storico, non cambia più


def test_storico_con_importo():
    provider = ExchangeProvider()
    result = provider.fetch({
        "from_currency": "USD", "to_currency": "EUR", "amount": 250, "date": "2020-01-02",
    })
    assert result["converted"] == round(250 * 0.89342, 2)


def test_giorno_non_lavorativo_segnala_la_data_usata():
    """domenica non ha fixing: si usa il precedente e lo si dichiara."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "EUR", "to_currency": "USD", "date": "2020-01-05"})
    assert "error" not in result
    assert result["date"] != "2020-01-05"
    assert result["requested_date"] == "2020-01-05"


def test_data_troppo_remota():
    """frankfurter parte dal 1999: prima non c'e' nulla."""
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "EUR", "to_currency": "USD", "date": "1980-01-01"})
    assert "error" not in result  # la data e' scartata, si ricade sul tasso corrente
    assert result["date"] > "1999-01-04"


def test_data_malformata_viene_ignorata():
    provider = ExchangeProvider()
    result = provider.fetch({"from_currency": "EUR", "to_currency": "USD", "date": "ieri"})
    assert "error" not in result
    assert "requested_date" not in result
