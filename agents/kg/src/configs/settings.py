from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # percorsi di base
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"

    # impostazioni Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_translation_model: str = "qwen2.5-coder:7b"
    ollama_timeout: float = 300.0

    # impostazioni Wikidata SPARQL
    sparql_endpoint: str = "https://query.wikidata.org/sparql"
    sparql_timeout: float = 15.0

    # impostazioni della pipeline
    default_target_kg: str = "wikidata"
    max_correction_retries: int = 3

settings = Settings()
