from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configurazione dell'agente, sovrascrivibile da variabili d'ambiente o file .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_translation_model: str = "qwen2.5-coder:7b"
    # il modello instruct generico disambigua le entità meglio di quello per codice
    ollama_linking_model: str = "qwen2.5:7b-instruct"
    ollama_timeout: float = 300.0

    sparql_endpoint: str = "https://query.wikidata.org/sparql"
    sparql_timeout: float = 15.0

    # l'endpoint pubblico DBpedia è più lento e soggetto a rate limit di quello Wikidata
    dbpedia_endpoint: str = "https://dbpedia.org/sparql"
    dbpedia_timeout: float = 30.0

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    # None = database di default dell'istanza (su Neo4j Community è sempre "neo4j")
    neo4j_database: str | None = None
    neo4j_timeout: float = 15.0

    # precarica i modelli locali all'avvio: sposta il costo del primo caricamento
    # fuori dalla prima domanda, che altrimenti lo pagherebbe tutto
    warmup_on_startup: bool = True

    default_target_kg: str = "wikidata"
    max_correction_retries: int = 3

settings = Settings()
