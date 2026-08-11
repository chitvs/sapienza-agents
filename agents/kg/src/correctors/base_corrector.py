from abc import ABC, abstractmethod

class BaseCorrector(ABC):
    """Interfaccia del correttore di query fallite."""

    @abstractmethod
    def correct(self, question: str, failed_query: str, error_message: str, schema_context: str = "") -> str:
        """Rigenera la query correggendo l'errore riscontrato."""
        raise NotImplementedError
