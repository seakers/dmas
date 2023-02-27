
from abc import ABC, abstractmethod
from enum import Enum
import logging

import zmq
from dmas.messages import *

from dmas.utils import *
from dmas.network import NetworkConfig, NetworkElement

class InternalModuleStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class InternalModuleNetworkConfig(NetworkConfig):
    """
    ## Internal Module Network Config
    
    Describes the addresses assigned to a node's internal module 
    """
    def __init__(self, 
                parent_pub_address: str,
                module_pub_address : str
                ) -> None:
        """
        Initializes an instance of an Internal Module Network Config Object
        
        ### Arguments:
        - parent_pub_address (`str`): a module's parent node's broadcast address
        - module_pub_address (`str`): the internal module's broadcast address
        """
        external_address_map = {zmq.SUB: [parent_pub_address], zmq.PUB: [module_pub_address]}       
        super().__init__(external_address_map=external_address_map)

class InternalModule(NetworkElement):
    """
    ## Internal Module

    Controls independent internal processes performed by a simulation node

    #### Attributes:
        - _submodules (`list`): submodules contained by this module
        - _internal_inbox (`asyncio.Queue()`):    
        - _external_inbox (`asyncio.Queue()`):
    ####
    """
    def __init__(self, module_name: str, parent_name : str, network_config: InternalModuleNetworkConfig, logger: logging.Logger, submodules : list = []) -> None:
        super().__init__(parent_name + '/' + module_name, network_config, logger.getEffectiveLevel(), logger)

        # copy submodule list
        self._submodules = []
        for submodule in submodules:

            # check submodule list's content types
            if isinstance(submodule, InternalSubmodule):
                self._submodules.append(submodule)
            else:
                raise AttributeError(f'contents of `submodules` list given to module {self.name} must be of type `SubModule`. Contains elements of type `{type(submodule)}`.')

        # initiate inboxes
        self._intermodule_inbox = asyncio.Queue()
        self._submodule_inbox = asyncio.Queue()

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

    def config_network(self) -> tuple:
        # configure own network ports
        self._external_socket_map, self._internal_socket_map = super().config_network()

        socket_maps = [self._external_socket_map, self._internal_socket_map]

        # Add parent module name as a topic subscription for all sub ports
        for map in socket_maps:
            for port_type in map:
                port_type : zmq.SocketType
                
                if port_type == zmq.SUB:
                    socket : zmq.Socket = self._external_address_ledger[port_type]
                    parent_module_name : str= self.get_parent_name()
                    socket.setsockopt(zmq.SUBSCRIBE, parent_module_name.encode('ascii'))          
                    self._external_address_ledger[port_type] = socket

        return self._external_socket_map, self._internal_socket_map

    async def _internal_sync(self) -> dict:
        # send a sync request to parent node
        sync_req = ModuleSyncRequestMessage(self.get_module_name(), self.get_parent_name())
        await self._send_internal_msg(sync_req, zmq.PUB)

        # wait for response from parent node
        while True:
            # listen for internal messages
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                continue

            if src not in self.get_parent_name():
                # received a message from an undesired sender. Ignoring message
                continue
            
            msg_type = msg_dict.get('@type', None)
            if msg_type is not None and NodeMessageTypes[msg_type] == NodeMessageTypes.RECEPTION_ACK:
                # received a sync request acknowledgement from the parent node. Sync complete!
                break

        # connections are static throughout the simulation. No ledger is required
        return dict()

    async def _external_sync(self) -> dict:
        # no external communications allowed for internal modules.  
        return dict()        
    
    def run(self):
        async def main():
            """
            Runs the following processes concurrently. All terminates if at least one of them does.
            """
            try:
                # perform this module's routine
                tasks = [asyncio.create_task(self.routine(), name=f'{self.name}_live')]

                # instruct all submodules to perform their own routines
                for submodule in self._submodules:
                    submodule : InternalSubmodule
                    tasks.append(submodule.routine(), name=f'{submodule.name}_live')

                # wait for a process to terminate
                _, pending = asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                
                # cancel all non-terminated tasks
                for task in pending:
                    task : asyncio.Task
                    task.cancel()
                    await task

                return 1
            
            except :
                return 0
            
            finally:
                # inform parent module that this module has terminated
                terminated_msg = TerminateInternalModuleMessage(self.name, self.get_parent_name())
                self._send_internal_msg(terminated_msg, zmq.PUB)
        
        return asyncio.run(main())

    @abstractmethod
    async def routine():
        """
        Routine to be performed by the module during when the parent node is executing.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

    @abstractmethod
    async def _listen(self):
        """
        Listens for messages from the parent node or other internal modules.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

class InternalSubmodule(ABC):
    def __init__(self, name : str, parent_name : str) -> None:
        super().__init__()
        self.name = parent_name + '/' + name
    
    async def routine() -> None:
        try:
            pass
        except asyncio.CancelledError:
            return