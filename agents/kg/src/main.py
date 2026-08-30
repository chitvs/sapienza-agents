import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

def _find_repo_root(start: Path) -> Path | None:
    """Risale da 'start' fino alla directory che contiene il pacchetto condiviso 'shared'."""
    for candidate in (start, *start.parents):
        if (candidate / "shared").is_dir():
            return candidate
    return None

src_dir = Path(__file__).resolve().parent
root_dir = _find_repo_root(src_dir)
if root_dir and str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import uvicorn
from fastapi import FastAPI
from api.routes import close_pipelines, router as api_router
from configs.settings import settings
from models.embeddings import SIMILARITY_MODEL_NAME, RETRIEVAL_MODEL_NAME, get_embedding_model
from models.mention_extraction import extract_entity_mentions

# configurazione logger
logger = logging.getLogger(__name__)

# librerie che a livello INFO registrano una riga per ogni richiesta http, da silenziare
_NOISY_LIBRARIES = ("httpx", "httpcore", "urllib3", "huggingface_hub", "filelock")

def _configure_logging() -> None:
    """Configura il logger radice."""
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    for name in _NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

_configure_logging()

def _warmup_models() -> None:
    """Carica in anticipo i modelli locali, altrimenti caricati alla prima domanda."""
    for model_name in (RETRIEVAL_MODEL_NAME, SIMILARITY_MODEL_NAME):
        get_embedding_model(model_name)
    extract_entity_mentions("warm up")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Precarica i modelli all'avvio e rilascia le connessioni ai grafi allo spegnimento."""
    if settings.warmup_on_startup:
        try:
            logger.info("precaricamento dei modelli locali...")
            _warmup_models()
            logger.info("modelli pronti.")
        except Exception as err:
            logger.warning("precaricamento fallito, si procede con caricamento pigro: %s", err)
    yield
    close_pipelines()

app = FastAPI(
    title="Knowledge graph Agent",
    description="Microservizio per interrogare knowledge graph in linguaggio naturale.",
    lifespan=lifespan,
)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
