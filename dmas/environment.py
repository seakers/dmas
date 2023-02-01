from beartype import beartype
from dmas.element import AbstractSimulationElement
from dmas.utils import *

# class AbstractEnvironmentElement(AbstractSimulationElement):
#     def __init__(self, name: str, network_config: EnvironmentNetworkConfig) -> None:
#         super().__init__(name, network_config)

if __name__ == "__main__":
    
    @beartype
    @abstractmethod
    def foo(x : int):
        pass
    
    foo(1)
    foo('x')
    