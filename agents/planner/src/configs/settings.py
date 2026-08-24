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
    gemini_timeout: float = 120.0

    # Configurazione Ollama (Fallback Locale)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: float = 2400.0

    # Configurazione OpenRouter (o provider OpenAI compatibili unificati)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_models: str = ""
    
    @property
    def parsed_openrouter_models(self) -> list[str]:
        """
        Restituisce la lista pulita dei modelli OpenRouter definiti nel .env.
        
        Returns:
            list[str]: Lista dei modelli, escludendo stringhe vuote.
        """
        return [m.strip() for m in self.openrouter_models.split(",") if m.strip()]

    # Pipeline: fallback
    max_draft_retries: int = 2
    max_json_retries: int = 1
    enable_local_fallback: bool = True

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