
from abc import ABC, abstractmethod
from enum import Enum
import logging

from dmas.utils import *
from dmas.network import NetworkElement

class InternalModuleStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class InternalModule(NetworkElement):
    """
    ## Internal Module

    Controls independent internal processes performed by a simulation node

    #### Attributes:
        - 
    
    ####
    """
    def __init__(self, module_name: str, parent_name : str, network_config: InternalModuleNetworkConfig, logger: logging.Logger, submodules : list = []) -> None:
        super().__init__(parent_name + '/' + module_name, network_config, logger.getEffectiveLevel(), logger)

        self._submodules = []
        for submodule in submodules:
            if isinstance(submodule, InternalSubmodule):
                self._submodules.append(submodule)
            else:
                raise AttributeError(f'contents of `submodules` list given to module {self.name} must be of type `SubModule`. Contains elements of type `{type(submodule)}`.')
            
        # TODO add parent module name topic subscription to sub port

    def get_name(self) -> str:
        """
        Returns full name of this module
        """
        return self.name

    def get_module_name(self) -> str:
        """
        Returns the name of this module
        """
        _, name = self.name.split('/')
        return name

    def get_parent_name(self) -> str:
        parent, _ = self.name.split('/')
        return parent

    async def _external_sync(self) -> dict:
        # no need to sync with parent node
        return dict()
    
    async def _internal_sync(self) -> dict:
        # no internal modules to sync with.  
        return None
    
    def run(self):
        async def main():
            tasks = [asyncio.create_task(self.routine())]

            for submodule in self._submodules:
                submodule : InternalSubmodule
                tasks.append(submodule.routine())

            _, pending = asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task : asyncio.Task
                task.cancel()
                await task
        
        asyncio.run(main())

    async def routine():
        pass

class InternalSubmodule(ABC):
    def __init__(self, name : str, parent_name : str) -> None:
        super().__init__()
        self.name = parent_name + '/' + name
    
    async def routine() -> None:
        pass