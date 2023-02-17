
from abc import ABC, abstractmethod
from enum import Enum
import logging
from dmas.element import SimulationElement

from dmas.utils import NetworkConfig

class InternalModuleStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class InternalModule(SimulationElement):
    """
    ## Internal Module

    Controls independent internal processes performed by a simulation node

    #### Attributes:
        - 
    
    ####
    """
    def __init__(self, name: str, network_config: NetworkConfig, logger: logging.Logger) -> None:
        super().__init__(name, network_config, logger=logger)

    @abstractmethod
    def activate(self) -> None:
        pass

    @abstractmethod
    def _config_network(self) -> None:
        pass

    @abstractmethod
    def _sync(self) -> None:
        pass

    @abstractmethod
    def _routine(self) -> None:
        pass

    @abstractmethod
    def _deactivate(self) -> None:
        pass
    
