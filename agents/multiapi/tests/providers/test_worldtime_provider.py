from providers.worldtime_provider import WorldTimeProvider


def test_fetch_tokyo():
    """il provider deve restituire l'ora corrente per Tokyo."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "Tokyo"})
    assert "error" not in result, f"errore inatteso: {result.get('error')}"
    assert result["provider"] == "timeapi"
    assert "Tokyo" in result["city"] or "Japan" in result["city"]
    assert result["timezone"] == "Asia/Tokyo"
    assert result["utc_offset"] == "+09:00"
    assert len(result["time"]) == 8   # HH:MM:SS
    assert len(result["date"]) == 10  # YYYY-MM-DD
    assert "datetime" in result


def test_fetch_rome():
    """il provider deve restituire l'ora corrente per Roma."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "Rome"})
    assert "error" not in result
    assert result["provider"] == "timeapi"
    assert result["timezone"] == "Europe/Rome"
    assert result["time"] != ""
    assert result["date"] != ""


def test_fetch_new_york():
    """il provider deve funzionare con nomi composti."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "New York"})
    assert "error" not in result
    assert result["timezone"] == "America/New_York"


def test_fetch_all_fields_present():
    """verifica che tutti i campi attesi siano presenti nella risposta."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "London"})
    assert "error" not in result
    expected_fields = [
        "provider", "city", "timezone", "datetime",
        "time", "date", "utc_offset", "abbreviation", "dst",
    ]
    for field in expected_fields:
        assert field in result, f"campo mancante: {field}"


def test_fetch_unknown_city():
    """il provider deve restituire un errore per una città inesistente."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "Xyznonexistent99999"})
    assert "error" in result


def test_fetch_empty_city():
    """il provider deve restituire un errore se la città è vuota."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": ""})
    assert "error" in result


def test_fetch_no_city_param():
    """il provider deve restituire un errore se manca il parametro city."""
    provider = WorldTimeProvider()
    result = provider.fetch({})
    assert "error" in result


def test_dst_field_is_bool():
    """il campo dst deve essere booleano."""
    provider = WorldTimeProvider()
    result = provider.fetch({"city": "Sydney"})
    if "error" not in result:
        assert isinstance(result["dst"], bool)
