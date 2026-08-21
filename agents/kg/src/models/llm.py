from pathlib import Path
from configs.settings import settings
from shared.ollama_client import OllamaClient

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "configs" / "prompts"

def build_llm_client(model_name: str | None = None) -> OllamaClient:
    """Costruisce il client Ollama secondo la configurazione dell'agente."""
    return OllamaClient(
        prompts_dir=PROMPTS_DIR,
        host=settings.ollama_host,
        model_name=model_name or settings.ollama_model,
        timeout=settings.ollama_timeout,
        num_ctx=settings.ollama_num_ctx,
    )
