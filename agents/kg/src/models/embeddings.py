import logging
from typing import Any

logger = logging.getLogger(__name__)

SIMILARITY_MODEL_NAME = "all-MiniLM-L6-v2"
RETRIEVAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# BGE è addestrato per retrieval asimmetrico: l'istruzione va solo sulle query, non sul
# corpus. Sposta il rank di P19 (place of birth) da 16 a 6 su 3309 proprietà.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_MODELS: dict[str, Any] = {}

def get_embedding_model(model_name: str = SIMILARITY_MODEL_NAME) -> Any:
    """Restituisce il modello sentence-transformers richiesto, caricandolo al primo uso."""
    if model_name not in _MODELS:
        logger.info("carico il modello sentence-transformers '%s'...", model_name)
        from sentence_transformers import SentenceTransformer

        _MODELS[model_name] = SentenceTransformer(model_name)
    return _MODELS[model_name]
