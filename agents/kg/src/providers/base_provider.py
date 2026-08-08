from abc import ABC, abstractmethod
from typing import Any

from configs.settings import settings
from connectors.base_connector import BaseConnector
from correctors.base_corrector import BaseCorrector
from executors.base_executor import BaseExecutor
from linkers.base_linker import BaseLinker
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
        # traduzione e linking usano modelli diversi ma spesso coincidono con quello
        # generale: la cache evita sessioni HTTP duplicate verso lo stesso modello
        if model_name not in self._clients:
            from shared.ollama_client import OllamaClient

            self._clients[model_name] = OllamaClient(
                host=settings.ollama_host,
                model_name=model_name,
                timeout=settings.ollama_timeout,
                prompts_dir=settings.prompts_dir,
            )
        return self._clients[model_name]

    @abstractmethod
    def _build_components(self) -> None:
        """Costruisce i componenti specifici del KG, assegnandoli agli attributi della classe."""
        raise NotImplementedError

    def get_connector(self) -> BaseConnector:
        return self.connector

    def get_linker(self) -> BaseLinker:
        return self.linker

    def get_translator(self) -> BaseTranslator:
        return self.translator

    def get_executor(self) -> BaseExecutor:
        return self.executor

    def get_pruner(self) -> BasePruner:
        return self.pruner

    def get_corrector(self) -> BaseCorrector | None:
        return self.corrector

    def get_llm_client(self) -> Any:
        return self.llm_client

    def get_linking_llm_client(self) -> Any:
        return self.linking_client
