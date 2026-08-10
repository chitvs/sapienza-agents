from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

current_path = Path(__file__).resolve().parent
ROOT_DIR = current_path
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "agents").exists():
        ROOT_DIR = parent
        break

class Settings(BaseSettings):
    """Unico posto per tutte le configurazioni dell'agente."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",  
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # percorsi
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"

    # Selezione del Provider: "gemini" oppure "ollama"
    llm_provider: str = "ollama"

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
    external_call_timeout: float = 60.0

settings = Settings()