from abc import ABC, abstractmethod

class BaseExecutor(ABC):

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, str]]:
        """
        Esegue la query sul database/triplestore e restituisce i risultati 
        formattati come una lista di dizionari (chiave: variabile, valore: stringa).
        """
        raise NotImplementedError
