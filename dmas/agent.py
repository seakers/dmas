from abc import ABC, abstractmethod


class AbstractAgent(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def activate(self) -> None:
        pass

    @abstractmethod
    def live(self) -> None:
        pass

    @abstractmethod
    def die(self) -> None:
        pass