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

    # Selezione del Provider: "gemini" oppure "ollama"
    llm_provider: str = "gemini"

    # Configurazione Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # Configurazione Ollama (Fallback Locale)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: float = 600.0

    # pipeline: dominio di fallback
    default_domain: str = "routine"
    max_draft_retries: int = 2

    # context gathering (Step 5)
    kg_agent_url: str = "http://localhost:8000"
    multiapi_agent_url: str = "http://localhost:8002"
    external_call_timeout: float = 5.0


settings = Settings()