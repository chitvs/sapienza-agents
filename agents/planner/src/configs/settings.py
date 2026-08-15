"""
Configurazione centralizzata dell'applicazione.

Gestisce il caricamento delle variabili d'ambiente (tramite pydantic-settings)
e definisce i parametri globali (timeout, modelli LLM, URL dei servizi).
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

current_path: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = current_path
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

    # Percorsi
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"

    # Selezione del Provider: "gemini" oppure "ollama"
    llm_provider: str = "ollama"

    # Configurazione Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout: float = 30.0

    # Configurazione Ollama (Fallback Locale)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: float = 600.0

    # Configurazioni multiple per provider OpenAI-compatibili (es. OpenRouter),
    # caricate come JSON da .env: la chiave è il nome del provider (lo stesso valore 
    # usabile in LLM_PROVIDER), il valore un dict con base_url/api_key/model.
    # Es. OPENAI_PROVIDERS={"openrouter_gpt": {"base_url": "...", "api_key": "...", "model": "..."}, ...}
    openai_providers: dict[str, dict[str, str]] = Field(default_factory=dict)

    # Pipeline: fallback
    max_draft_retries: int = 2

    # Context gathering 
    kg_agent_url: str = "http://localhost:8000"
    multiapi_agent_url: str = "http://localhost:8002"
    external_call_timeout: float = 60.0

    context_gathering_mode: Literal["deterministic", "react", "none"] = "react"
    max_react_steps: int = 3

    # Planner: verbosità pipeline (log della risposta grezza dell'llm, ecc.)
    planner_verbose: bool = True

    # Pipeline: euristica di confidence
    confidence_retry_penalty: float = 0.25
    confidence_context_error_penalty: float = 0.1
    confidence_floor: float = 0.5

    # Messaggi statici
    out_of_scope_message: str = (
        "Questa richiesta non riguarda pianificazione di studio, itinerari di viaggio o "
        "routine giornaliere: il planner-agent non genera un piano per questo tipo di domanda."
    )


settings: Settings = Settings()