from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Unico posto per tutte le configurazioni dell'agente."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # percorsi
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"

    # ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: float = 180.0

    # open-meteo (nessuna api key necessaria)
    open_meteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"

    # cambio valuta (senza api key)
    frankfurter_base_url: str = "https://api.frankfurter.app"

    # info paesi via countries.dev (senza api key)
    countries_dev_base_url: str = "https://countries.dev"

    # cache
    cache_capacity: int = 100

    # corrector (retry llm per json non valido)
    max_llm_retries: int = 2


settings = Settings()
