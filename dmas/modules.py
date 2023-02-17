
from abc import ABC, abstractmethod
from enum import Enum
import logging

from dmas.utils import *

class InternalModuleStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class InternalModule(ABC):
    """
    ## Internal Module

    Controls independent internal processes performed by a simulation node

    #### Attributes:
        - 
    
    ####
    """
    def __init__(self, module_name: str, parent_name : str, network_config: InternalModuleNetworkConfig, logger: logging.Logger) -> None:
        super().__init__()
        self.name = module_name + '/' + parent_name
        self._network_config = network_config

    def get_name(self) -> str:
        """
        Returns full name of this module
        """
        return self.name

    def get_module_name(self) -> str:
        """
        Returns the name of this module
        """
        name, _ = self.name.split('/')
        return name

    def get_parent_name(self) -> str:
        _, parent = self.name.split('/')
        return parent

    @abstractmethod
    def config_network(self) -> None:
        pass

    @abstractmethod
    def sync(self) -> None:
        pass

    @abstractmethod
    async def _routine(self) -> None:
        pass

    def run(self) -> None:
        try:
            asyncio.run(self._routine())
        finally:
            self._deactivate()

    @abstractmethod
    def _deactivate(self) -> None:
        pass
    
