from abc import ABC, abstractmethod
from typing import Any
from configs.settings import settings
from connectors.base_connector import BaseConnector
from correctors.base_corrector import BaseCorrector
from executors.base_executor import BaseExecutor
from linkers.base_linker import BaseLinker
from models.llm import build_llm_client
from pruners.base_pruner import BasePruner
from translators.base_translator import BaseTranslator

class BaseProvider(ABC):
    """Abstract Factory dei componenti specifici di un knowledge graph."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        self.llm_client = self._client_for(settings.ollama_model)
        self.translation_client = self._client_for(settings.ollama_translation_model)
        self.linking_client = self._client_for(settings.ollama_linking_model)
        self.connector: BaseConnector
        self.linker: BaseLinker
        self.translator: BaseTranslator
        self.executor: BaseExecutor
        self.pruner: BasePruner
        self.corrector: BaseCorrector | None
        self._build_components()

    def _client_for(self, model_name: str) -> Any:
        """Restituisce il client Ollama del modello, riusandolo se già creato."""
        if model_name not in self._clients:
            self._clients[model_name] = build_llm_client(model_name)
        return self._clients[model_name]

    @abstractmethod
    def _build_components(self) -> None:
        """Costruisce i componenti specifici del KG, assegnandoli agli attributi della classe."""
        raise NotImplementedError
