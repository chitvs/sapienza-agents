import logging
from typing import Any
from configs.settings import settings

logger = logging.getLogger(__name__)

_MODEL_NAME = "urchade/gliner_mediumv2.1"

# Categorie generiche di soggetti su cui si interroga un KG generalista
_ENTITY_LABELS = [
    "person",
    "organization",
    "location",
    "creative work",
    "event",
    "product",
    "nationality",
]

# Soglia orientata al recall: GLiNER non separa in modo affidabile le entità vere dai
# sostantivi di ruolo ("coach" a volte scora più in alto di "penicillin"), quindi la
# precisione è delegata al filtro LLM successivo invece di inseguire una soglia che,
# per costruzione, non esiste.

_MODEL: Any = None

def _get_model() -> Any:
    """Carica il modello GLiNER al primo uso."""
    global _MODEL
    if _MODEL is None:
        logger.info("carico il modello GLiNER per l'estrazione zero-shot delle entità...")
        from gliner import GLiNER

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
