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
    ollama_timeout: float = 600.0

    # pipeline: dominio di fallback se la classificazione fallisce o restituisce 'unknown'
    default_domain: str = "routine"

    # pipeline: numero massimo di tentativi di correzione se il draft non supera la validazione logica
    max_draft_retries: int = 2

    # context gathering (Step 5): agenti esterni interrogati per il dominio 'travel'.
    # default 'localhost' pensati per sviluppo locale; sovrascritti via env var
    # (KG_AGENT_URL / MULTIAPI_AGENT_URL) dagli hostname interni alla rete docker-compose.
    kg_agent_url: str = "http://localhost:8000"
    multiapi_agent_url: str = "http://localhost:8002"
    external_call_timeout: float = 5.0  # per singola chiamata, non cumulativo


settings = Settings()