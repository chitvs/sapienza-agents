from providers.country_provider import CountryProvider
from conftest import richiede_countries_dev

# interrogano il servizio vero: senza rete si saltano, non falliscono
pytestmark = richiede_countries_dev


def test_fetch_france():
    """il provider deve restituire dati validi per la Francia."""
    provider = CountryProvider()
    result = provider.fetch({"country": "France"})
    assert "error" not in result
    assert result["provider"] == "countries.dev"
    assert result["name"] == "France"
    assert result["capital"] == "Paris"
    assert result["population"] > 0
    assert result["area_km2"] > 0
    assert "French" in result["languages"]
    assert any(c["code"] == "EUR" for c in result["currencies"])


def test_fetch_japan():
    """il provider deve funzionare con paesi non europei."""
    provider = CountryProvider()
    result = provider.fetch({"country": "Japan"})
    assert "error" not in result
    assert result["name"] == "Japan"
    assert result["capital"] == "Tokyo"
    assert result["region"] == "Asia"
    assert len(result["timezones"]) > 0


def test_fetch_italy_fields():
    """verifica che tutti i campi attesi siano presenti nella risposta."""
    provider = CountryProvider()
    result = provider.fetch({"country": "Italy"})
    assert "error" not in result
    expected_fields = [
        "provider", "name", "native_name", "capital", "region",
        "subregion", "population", "area_km2", "languages",
        "currencies", "timezones", "borders", "flag_emoji",
    ]
    for field in expected_fields:
        assert field in result, f"campo mancante: {field}"
    # countries.dev non espone un nome ufficiale ne' i link alle mappe: esporli
    # copiando altri campi dava valori sbagliati o sempre vuoti
    assert "official_name" not in result
    assert "maps_url" not in result
    assert result["capital"] == "Rome"
    assert len(result["borders"]) > 0  # Italia confina con diversi paesi


def test_fetch_unknown_country():
    """il provider deve restituire un errore per un paese inesistente."""
    provider = CountryProvider()
    result = provider.fetch({"country": "Xyzlandia"})
    assert "error" in result


def test_fetch_empty_country():
    """il provider deve restituire un errore se il paese è vuoto."""
    provider = CountryProvider()
    result = provider.fetch({"country": ""})
    assert "error" in result


def test_fetch_no_country_param():
    """il provider deve restituire un errore se manca il parametro country."""
    provider = CountryProvider()
    result = provider.fetch({})
    assert "error" in result
