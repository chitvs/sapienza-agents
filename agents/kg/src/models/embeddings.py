import logging
import threading
from typing import Any
from sentence_transformers import SentenceTransformer

# configurazione logger
logger = logging.getLogger(__name__)

# variabili globali
SIMILARITY_MODEL_NAME = "all-MiniLM-L6-v2"
RETRIEVAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_MODELS: dict[str, Any] = {}
# gli endpoint sono sincroni e FastAPI li serve da un threadpool, serve il lock.
_MODELS_LOCK = threading.Lock()

def get_embedding_model(model_name: str = SIMILARITY_MODEL_NAME) -> Any:
    """Restituisce il modello sentence-transformers richiesto, caricandolo al primo uso."""
    with _MODELS_LOCK:
        if model_name not in _MODELS:
            logger.info("carico il modello sentence-transformers '%s'...", model_name)
            _MODELS[model_name] = SentenceTransformer(model_name)
        return _MODELS[model_name]
