from providers.weather_provider import WeatherProvider
from conftest import richiede_open_meteo

# interrogano il servizio vero: senza rete si saltano, non falliscono
pytestmark = richiede_open_meteo


def test_geocode_roma():
    """il geocoding deve trovare Roma con coordinate plausibili."""
    provider = WeatherProvider()
    location = provider._geocode("Roma")
    assert location is not None
    assert abs(location["latitude"] - 41.89) < 1
    assert abs(location["longitude"] - 12.51) < 1


def test_geocode_unknown_city():
    """il geocoding deve restituire None per una città inesistente."""
    provider = WeatherProvider()
    location = provider._geocode("Xyznonexistent12345")
    assert location is None


def test_fetch_weather():
    """il provider deve restituire dati meteo validi per una città reale."""
    provider = WeatherProvider()
    result = provider.fetch({"city": "Roma"})
    assert "error" not in result
    assert result["provider"] == "open-meteo"
    assert "temperature_c" in result
    assert "condition" in result
    assert "humidity_percent" in result
    assert "wind_speed_kmh" in result
    assert isinstance(result["temperature_c"], (int, float))


def test_fetch_unknown_city():
    """il provider deve restituire un errore per una città inesistente."""
    provider = WeatherProvider()
    result = provider.fetch({"city": "Xyznonexistent12345"})
    assert "error" in result


def test_fetch_empty_city():
    """il provider deve restituire un errore se la città è vuota."""
    provider = WeatherProvider()
    result = provider.fetch({"city": ""})
    assert "error" in result


def test_fetch_no_city_param():
    """il provider deve restituire un errore se manca il parametro city."""
    provider = WeatherProvider()
    result = provider.fetch({})
    assert "error" in result
