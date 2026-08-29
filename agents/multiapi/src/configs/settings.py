from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nel repo parents[2] è la cartella dell'agente e parents[4] la root, ma nel
# container il Dockerfile copia solo src/ dentro /app e quei livelli non
# esistono: gli indici oltre la profondità disponibile vanno scartati.
_PARENTS = Path(__file__).resolve().parents
_ENV_FILES = tuple(
    _PARENTS[i] / ".env"
    for i in (4, 2)          # prima la root, poi la cartella dell'agente
    if i < len(_PARENTS)     # l'ultimo file vince sui precedenti
)


class Settings(BaseSettings):
    """Unico posto per tutte le configurazioni dell'agente."""

    model_config = SettingsConfigDict(
        # percorsi assoluti: così i .env vengono trovati anche lanciando pytest
        # da una cartella diversa. I file inesistenti vengono ignorati.
        env_file=_ENV_FILES,
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

    # cambio valuta (senza api key).
    frankfurter_base_url: str = "https://api.frankfurter.dev/v1"

    # info paesi via countries.dev (senza api key)
    countries_dev_base_url: str = "https://countries.dev"

    # ora locale via world-time-api3 su RapidAPI 
    # richiede una api key: TIMEAPI_API_KEY nel .env (vedi .env.example)
    worldtime_base_url: str = "https://world-time-api3.p.rapidapi.com/timezone"
    worldtime_api_host: str = "world-time-api3.p.rapidapi.com"
    timeapi_api_key: str = ""


    # cache
    cache_capacity: int = 100
    # Validità in cache per intent, proporzionata alla volatilità del dato.
    # 0 disabilita la memorizzazione.
    cache_ttl_default: float = 300.0
    cache_ttl_by_intent: dict[str, float] = {
        "time_info": 0.0,        # è un orologio: una risposta riusata è per definizione sbagliata
        "weather": 600.0,        # open-meteo aggiorna il dato corrente ogni ~15 min
        "exchange_rate": 3600.0, # frankfurter pubblica un fixing al giorno
        "country_info": 86400.0, # capitale, superficie e lingue non cambiano
    }

    # quanti intent servire per una singola domanda: ognuno in più costa una
    # chiamata al llm per l'estrazione dei parametri e una all'api esterna
    max_intents_per_question: int = 2

    # corrector (retry llm per json non valido)
    max_llm_retries: int = 2

    # log passo-passo della pipeline
    verbose_pipeline: bool = False


settings = Settings()
