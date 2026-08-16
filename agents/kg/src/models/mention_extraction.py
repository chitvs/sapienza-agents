import logging
import threading
from typing import Any
from gliner import GLiNER
from configs.settings import settings

# configurazione logger
logger = logging.getLogger(__name__)

# variabili globali
_MODEL_NAME = "urchade/gliner_mediumv2.1"

# categorie generiche di soggetti su cui si interroga un KG generalista
_ENTITY_LABELS = [
    "person",
    "organization",
    "location",
    "creative work",
    "event",
    "product",
    "nationality",
]

_MODEL: Any = None
_MODEL_LOCK = threading.Lock()

def _get_model() -> Any:
    """Carica il modello GLiNER al primo uso."""
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            logger.info("carico il modello GLiNER per l'estrazione zero-shot delle entità...")
            _MODEL = GLiNER.from_pretrained(_MODEL_NAME)
        return _MODEL

def extract_entity_mentions(text: str) -> list[str]:
    """Estrae le menzioni di entità dal testo tramite NER zero-shot, senza duplicati."""
    # essendo un modello di span-extraction e non generativo, non può restituire
    # entità che non compaiono letteralmente nel testo
    entities = _get_model().predict_entities(text, _ENTITY_LABELS, threshold=settings.gliner_score_threshold)

    seen: set[str] = set()
    mentions: list[str] = []
    for ent in entities:
        mention = ent["text"].strip()
        if mention and mention.lower() not in seen:
            seen.add(mention.lower())
            mentions.append(mention)
    return mentions
