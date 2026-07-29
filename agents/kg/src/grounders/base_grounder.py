from abc import ABC, abstractmethod

class BaseGrounder(ABC):

    @abstractmethod
    def ground(self, raw_results: list[dict]) -> list[dict]:
        raise NotImplementedError
