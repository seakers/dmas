
from abc import ABC, abstractmethod
from enum import Enum
import logging
import random

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
                network_name : str,
                parent_pub_address: str,
                module_pub_address : str
                ) -> None:
        """
        Initializes an instance of an Internal Module Network Config Object
        
        ### Arguments:
        - parent_pub_address (`str`): a module's parent node's broadcast address
        - module_pub_address (`str`): the internal module's broadcast address
        """
        internal_address_map = {zmq.SUB: [parent_pub_address], 
                                zmq.PUB: [module_pub_address]}       
        super().__init__(network_name, internal_address_map=internal_address_map)

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
    def __init__(self, module_name: str, network_config: InternalModuleNetworkConfig, submodules : list = [], level : int = logging.INFO, logger: logging.Logger = None) -> None:
        super().__init__(module_name, network_config, logger=logger)
        self._clock_config = None

        # copy submodule list
        self._submodules = []
        for submodule in submodules:

            # check submodule list's content types
            if isinstance(submodule, InternalSubmodule):
                self._submodules.append(submodule)
            else:
                raise AttributeError(f'contents of `submodules` list given to module {self.name} must be of type `SubModule`. Contains elements of type `{type(submodule)}`.')

    def get_name(self) -> str:
        """
        Returns full name of this module
        """
        return self.name

    def get_module_name(self) -> str:
        """
        Returns the name of this module
        """
        return self._element_name

    def get_parent_name(self) -> str:
        """
        Returns the name of this module's parent network node
        """
        return self._network_name       

    async def network_sync(self) -> tuple:
        self._log(f'syncing with parent node {self.get_parent_name()}...', level=logging.INFO) 
        while True:
            # send sync request from REQ socket
            sync_req = ModuleSyncRequestMessage(self.get_module_name(), self.get_parent_name())
            dst, src, content = await self._send_internal_request_message(sync_req)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self._log(f'received message intended for {dst}. Ignoring...')
                continue

            elif self.get_parent_name() != src:
                # received a message from an undesired external sender. Ignoring message
                self._log(f'received message from someone who is not the parent node. Ignoring...')
                continue

            elif msg_type == NodeMessageTypes.RECEPTION_ACK.value:
                # received a sync request acknowledgement from the parent node. Sync complete!
                self._log(f'sync request accepted!', level=logging.INFO)
                break
            else:
                self._log(f'sync request not accepted. trying again later...')
                await asyncio.wait(random.random())
                
        # wait for node information message
        self._log('waiting for simulation information message from parent node...') 
        while True:
            # wait for response from parent node and listen for internal messages
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self._log(f'received message intended for {dst}. Ignoring...')
                continue

            if self.get_parent_name() != src:
                # received a message from an undesired external sender. Ignoring message
                self._log(f'received message from someone who is not the parent node. Ignoring...')
                continue
            
            msg_type = msg_dict.get('msg_type', None)
            if msg_type == NodeMessageTypes.NODE_INFO.value:
                # received a node information message from the parent node!
                self._log(f'simulation information message recevied! sync complete.', level=logging.INFO)
                resp = NodeInfoMessage(**msg_dict)
                break
            else:
                self._log(f'received undesired message of type {msg_type}. Ignoring...')
        
        # connections are static throughout the simulation. No ledger is required
        return resp.get_clock_config(), dict(), dict()           
    
    def run(self):                
        self._log('running...')
        return asyncio.run(self.main())

    async def main(self):
        """
        Runs the following processes concurrently. All terminates if at least one of them does.
        """
        try:
            # configure own network ports
            self._log(f'configuring network...')
            asyncio.sleep(0.1)
            self._network_context, self._external_socket_map, self._internal_socket_map = super().config_network()
            self._log(f'NETWORK CONFIGURED!', level = logging.INFO)
            
            # sync network 
            self._log(f'syncing network...')
            self._clock_config, _, _ = await self.network_sync()
            self._log(f'NETWORK SYNCED!', level = logging.INFO)

            # perform this module's routine
            self._log(f'starting internal routines...')
            tasks = [asyncio.create_task(self._routine(), name=f'{self.name}_routine'),
                        asyncio.create_task(self._listen(), name=f'{self.name}_listen'),]

            # instruct all submodules to perform their own routines
            self._log(f'starting submodule routines...')
            for submodule in self._submodules:
                submodule : InternalSubmodule
                tasks.append(submodule.run(), name=f'{submodule.name}_run')

            # wait for a process to terminate
            self._log(f'running...')
            done, pending = asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            # cancel all non-terminated tasks
            for task in done:
                task : asyncio.Task
                self._log(f'{task.get_name()} TERMINATED! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                self._log(f'terminaitng {task.get_name()}...')
                task.cancel()
                await task
                self._log(f'{task.get_name()} successfully terminated!')

            return 1
        
        except :
            return 0
        
        finally:
            # inform parent module that this module has terminated
            await self._publish_deactivate()

            # close network connections
            self._deactivate_network()

    async def _publish_deactivate(self) -> None:
        self._log(f'informing parent node of module termination...')
        while True:
            # send sync request from REQ socket
            terminated_msg = TerminateInternalModuleMessage(self.name, self.get_parent_name())
            dst, src, content = await self._send_internal_request_message(terminated_msg)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self._log(f'received message intended for {dst}. Ignoring...')
                continue

            elif self.get_parent_name() != src:
                # received a message from an undesired external sender. Ignoring message
                self._log(f'received message from someone who is not the parent node. Ignoring...')
                continue

            elif msg_type == NodeMessageTypes.RECEPTION_ACK.value:
                # received a sync request acknowledgement from the parent node. Sync complete!
                self._log(f'message accepted! parent node knows of my termination!', level=logging.INFO)
                break
            else:
                self._log(f'message not accepted. trying again later...')
                await asyncio.wait(random.random())

    @abstractmethod
    async def _routine():
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
    def __init__(self, name : str, parent_module_name : str, submodules : list = []) -> None:
        super().__init__()
        self.name = parent_module_name + '/' + name
        self._submodules = submodules
    
    async def run(self) -> None:
        """
        Runs the following processes concurrently. All terminates if at least one of them does.
        """
        try:
            try:
                # perform this module's routine
                tasks = [asyncio.create_task(self._routine(), name=f'{self.name}_routine'),
                         asyncio.create_task(self._listen(), name=f'{self.name}_listen'),]

                # instruct all submodules to perform their own routines
                for submodule in self._submodules:
                    submodule : InternalSubmodule
                    tasks.append(submodule.run(), name=f'{submodule.name}_run')

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

        except asyncio.CancelledError:
            return
        
    @abstractmethod
    async def _routine():
        """
        Routine to be performed by the submodule during when the parent module is executing.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

    @abstractmethod
    async def _listen(self):
        """
        Listens for messages from the other internal modules.

        Must have an `asyncio.CancellationError` handler.
        """
        pass