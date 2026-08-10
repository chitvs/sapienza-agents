from configs.settings import settings
from shared.ollama_client import OllamaClient

def build_llm_client(model_name: str | None = None, host: str | None = None) -> OllamaClient:
    """Costruisce il client Ollama secondo la configurazione dell'agente."""
    return OllamaClient(
        host=host or settings.ollama_host,
        model_name=model_name or settings.ollama_model,
        timeout=settings.ollama_timeout,
        prompts_dir=settings.prompts_dir,
        num_ctx=settings.ollama_num_ctx,
    )
