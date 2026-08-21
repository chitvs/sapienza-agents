from configs.settings import settings


def test_defaults():
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.cache_capacity == 100
    assert settings.max_llm_retries == 2


def test_provider_urls():
    assert "open-meteo" in settings.open_meteo_geocoding_url
    assert "open-meteo" in settings.open_meteo_forecast_url
    assert "frankfurter" in settings.frankfurter_base_url
    assert "countries" in settings.countries_dev_base_url
    assert "world-time-api3" in settings.worldtime_base_url
    assert settings.worldtime_api_host in settings.worldtime_base_url


def test_prompts_exist():
    assert settings.prompts_dir.exists()
    assert (settings.prompts_dir / "classify_intent.txt").exists()
    assert (settings.prompts_dir / "extract_city.txt").exists()
    assert (settings.prompts_dir / "extract_exchange.txt").exists()
    assert (settings.prompts_dir / "extract_country.txt").exists()
    assert (settings.prompts_dir / "extract_timezone.txt").exists()
