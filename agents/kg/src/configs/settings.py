from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configurazione dell'agente, sovrascrivibile da variabili d'ambiente o file .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_translation_model: str = "qwen2.5-coder:7b"
    ollama_linking_model: str = "qwen2.5:7b-instruct"
    ollama_timeout: float = 300.0

    wikidata_endpoint: str = "https://query.wikidata.org/sparql"
    wikidata_timeout: float = 15.0

    dbpedia_endpoint: str = "https://dbpedia.org/sparql"
    dbpedia_timeout: float = 30.0 # è più lento rispetto all'endpoint di wikidata

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str | None = None
    neo4j_timeout: float = 15.0

    warmup_on_startup: bool = True # precarica i modelli locali all'avvio

    default_target_kg: str = "wikidata"
    max_correction_retries: int = 3
    retry_backoff_seconds: float = 2.0

    linker_candidates: int = 15 # numero di candidati recuperati per menzione

    # Soglia orientata al richiamo: GLiNER non separa in modo affidabile le entità vere
    # dai sostantivi di ruolo ("coach" a volte scora più in alto di "penicillin"), quindi
    # la precisione è delegata al filtro LLM successivo invece che a una soglia che, per
    # costruzione, non esiste. Sotto 0.35 estrae frammenti, sopra perde menzioni.
    gliner_score_threshold: float = 0.35

    # ampiezza della ricerca vettoriale nell'ontologia: è il bacino da cui si estraggono
    # le proprietà verificate, non il numero di quelle mostrate
    schema_search_pool: int = 25

    # proprietà soltanto suggerite mostrate al modello: cresce il contesto, cresce la
    # confusione, e con bge-small le proprietà giuste per domande indirette stanno nel top-15
    schema_max_suggested: int = 15

    # la finestra deve contenere prompt, schema e few-shot: se trabocca il modello perde
    # le istruzioni iniziali senza che nulla lo segnali
    ollama_num_ctx: int = 8192
    cache_capacity: int = 100

    # 0.9405 separa "quanti film" da "quali film", 0.9442 una vera parafrasi: la soglia
    # sta sotto entrambe e la partizione per intento fa il resto
    cache_similarity_threshold: float = 0.92

    retry_temperature: float = 1.0
    retry_top_p: float = 0.9

    # impostazioni dei log:
    # INFO mostra i log
    # WARNING li silenzia
    log_level: str = "INFO"

settings = Settings()
