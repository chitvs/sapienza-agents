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

    # pipeline: dominio di fallback se la classificazione fallisce o restituisce 'unknown'
    default_domain: str = "routine"


settings = Settings()