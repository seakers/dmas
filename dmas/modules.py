
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
    def __init__(self, module_name: str, module_network_config: NetworkConfig, parent_network_config: NetworkConfig, submodules : list = [], level : int = logging.INFO, logger: logging.Logger = None) -> None:
        super().__init__(module_name, module_network_config, level=level, logger=logger)

        # check arguments
        if zmq.REQ not in module_network_config.get_manager_addresses():
            raise AttributeError(f'`module_network_config` must contain a REQ port and an address to parent node within manager address map.')
        if zmq.SUB not in module_network_config.get_manager_addresses():
            raise AttributeError(f'`module_network_config` must contain a SUB port and an address to parent node within manager address map.')
        if not isinstance(parent_network_config, NetworkConfig) and parent_network_config is not None:
            raise AttributeError(f'`parent_network_config` must be of type `NetworkConfig`. is of type {type(parent_network_config)}')

        # initialize attributes
        self._clock_config = None
        self._manager_address_ledger = {self.get_parent_name() : parent_network_config}
        
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

    async def _network_sync(self) -> tuple:
        self.log(f'syncing with parent node {self.get_parent_name()}...', level=logging.INFO) 
        while True:
            # send sync request from REQ socket
            sync_req = ModuleSyncRequestMessage(self.get_module_name(), self.get_parent_name())
            dst, _, content = await self._send_manager_request_message(sync_req)
            dst : str; content : dict
            msg_type = content['msg_type']

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self.log(f'received message intended for {dst}. Ignoring...')
                continue

            elif self.get_parent_name() != content['src']:
                # received a message from an undesired external sender. Ignoring message
                self.log(f'received message from someone who is not the parent node. Ignoring...')
                continue

            elif msg_type == NodeMessageTypes.RECEPTION_ACK.value:
                # received a sync request acknowledgement from the parent node. Sync complete!
                self.log(f'sync request accepted!', level=logging.INFO)
                break
            else:
                self.log(f'sync request not accepted. trying again later...')
                await asyncio.wait(random.random())
                
        # wait for node information message
        self.log('waiting for simulation information message from parent node...') 
        while True:
            # wait for response from parent node and listen for internal messages
            dst, _, msg_dict = await self._receive_manager_msg(zmq.SUB)
            dst : str; msg_dict : dict

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self.log(f'received message intended for {dst}. Ignoring...')
                continue

            if self.get_parent_name() != content['src']:
                # received a message from an undesired external sender. Ignoring message
                self.log(f'received message from someone who is not the parent node. Ignoring...')
                continue
            
            msg_type = msg_dict.get('msg_type', None)
            if msg_type == NodeMessageTypes.NODE_INFO.value:
                # received a node information message from the parent node!
                self.log(f'simulation information message recevied! sync complete.', level=logging.INFO)
                resp = NodeInfoMessage(**msg_dict)
                break
            else:
                self.log(f'received undesired message of type {msg_type}. Ignoring...')
        
        # connections are static throughout the simulation. No ledger is required
        return resp.get_clock_config(), dict(), dict()    
    
    def run(self):                
        self.log('running...')
        return asyncio.run(self.main())

    async def main(self):
        """
        Runs the following processes concurrently. All terminates if at least one of them does.
        """
        try:
            # wait for parent node to configure their network ports
            tasks, done, pending = None, None, None
            await asyncio.sleep(random.random())

            # configure own network ports
            self.log(f'configuring network...')
            self._network_context, self._manager_socket_map, self._external_socket_map, self._internal_socket_map = super()._config_network()
            self.log(f'NETWORK CONFIGURED!', level = logging.INFO)
            
            # sync network 
            self.log(f'syncing network...')
            self._clock_config, _, _ = await self._network_sync()
            self.log(f'NETWORK SYNCED!', level = logging.INFO)

            # wait for sim start
            self.log(f'waiting on sim start...')
            await self._wait_sim_start()
            self.log(f'SIM STARTED!', level = logging.INFO)

            # perform this module's routine
            self.log(f'starting internal routines...')
            tasks = [asyncio.create_task(self.routine(), name=f'{self.name}_routine'),
                        asyncio.create_task(self.listen(), name=f'{self.name}_listen'),
                        asyncio.create_task(self.listen_for_manager(), name=f'{self.name}_listen_manager')]

            # instruct all submodules to perform their own routines
            self.log(f'starting submodule routines...')
            for submodule in self._submodules:
                submodule : InternalSubmodule
                tasks.append(submodule.run(), name=f'{submodule.name}_run')

            # wait for a process to terminate
            self.log(f'running...')
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            return 1
        
        except :
            return 0
        
        finally:
            # cancel all non-terminated tasks
            if done is not None and pending is not None:
                for task in done:
                    task : asyncio.Task
                    self.log(f'{task.get_name()} TERMINATED! Terminating all other tasks...')

                for task in pending:
                    task : asyncio.Task
                    self.log(f'terminaitng {task.get_name()}...')
                    task.cancel()
                    await task
                    self.log(f'{task.get_name()} successfully terminated!')

            elif tasks is not None:
                self.log(f'Terminating all other tasks...')
                for task in tasks:
                    task : asyncio.Task
                    self.log(f'terminaitng {task.get_name()}...')
                    task.cancel()
                    await task
                    self.log(f'{task.get_name()} successfully terminated!')

            # inform parent module that this module has terminated
            await self._publish_deactivate()

            # close network connections
            self._deactivate_network()
    
    async def _wait_sim_start(self) -> None:
        # inform parent node of ready status
        self.log(f'informing parent node of ready status...', level=logging.INFO) 
        while True:
            # send sync request from REQ socket
            sync_req = ModuleReadyMessage(self.get_module_name(), self.get_parent_name())
            dst, _, content = await self._send_manager_request_message(sync_req)
            dst : str; _ : str; content : dict
            msg_type = content['msg_type']

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self.log(f'received message intended for {dst}. Ignoring...')
                continue

            elif self.get_parent_name() != content['src']:
                # received a message from an undesired external sender. Ignoring message
                self.log(f'received message from someone who is not the parent node. Ignoring...')
                continue

            elif msg_type == NodeMessageTypes.RECEPTION_ACK.value:
                # received a sync request acknowledgement from the parent node. Sync complete!
                self.log(f'module ready message accepted! waiting for simulation start message from parent node...', level=logging.INFO)
                break
            else:
                self.log(f'module ready message not accepted. trying again later...')
                await asyncio.wait(random.random())
                
        # wait for node information message
        while True:
            # wait for response from parent node and listen for internal messages
            dst, _, msg_dict = await self._receive_manager_msg(zmq.SUB)
            dst : str; _ : str; msg_dict : dict

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self.log(f'received message intended for {dst}. Ignoring...')
                continue

            if self.get_parent_name() != content['src']:
                # received a message from an undesired external sender. Ignoring message
                self.log(f'received message from someone who is not the parent node. Ignoring...')
                continue
            
            msg_type = msg_dict.get('msg_type', None)
            if msg_type == NodeMessageTypes.MODULE_ACTIVATE.value:
                # received sim start message from the parent node!
                self.log(f'simulation start message received! starting simulation...', level=logging.INFO)
                break
            else:
                self.log(f'received undesired message of type {msg_type}. Ignoring...')

    async def _publish_deactivate(self) -> None:
        self.log(f'informing parent node of module termination...')
        while True:
            # send sync request from REQ socket
            terminated_msg = ModuleDeactivatedMessage(self.name, self.get_parent_name())
            dst, _, content = await self._send_manager_request_message(terminated_msg)
            dst : str; content : dict
            msg_type = content['msg_type']

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                self.log(f'received message intended for {dst}. Ignoring...')
                continue

            elif self.get_parent_name() != content['src']:
                # received a message from an undesired external sender. Ignoring message
                self.log(f'received message from someone who is not the parent node. Ignoring...')
                continue

            elif msg_type == NodeMessageTypes.RECEPTION_ACK.value:
                # received a sync request acknowledgement from the parent node. Sync complete!
                self.log(f'message accepted! parent node knows of my termination!', level=logging.INFO)
                break
            
            else:
                self.log(f'message not accepted. trying again later...')
                await asyncio.wait(random.random())

    @abstractmethod
    async def routine():
        """
        Routine to be performed by the module during when the parent node is executing.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

    @abstractmethod
    async def listen(self):
        """
        Listens for messages from the parent node or other internal modules.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

    async def listen_for_manager(self):
        """
        Listens for any messages from the parent node. 

        By default it only listens for deactivation broadcasts.
        """
        try:
            self.log(f'waiting for parent module to deactivate me...')
            while True:
                dst, src, content = await self._receive_manager_msg(zmq.SUB)

                if (dst not in self.name 
                    or self.get_parent_name() not in src 
                    or content['msg_type'] != NodeMessageTypes.MODULE_DEACTIVATE.value):
                    self.log('wrong message received. ignoring message...')
                else:
                    self.log('deactivate module message received! ending simulation...')
                    break

        except asyncio.CancelledError:
            self.log(f'`_listen()` interrupted. {e}')
            return
        except Exception as e:
            self.log(f'`_listen()` failed. {e}')
            raise e

    async def _send_manager_request_message(self, msg : SimulationMessage) -> list:
        """
        Sends a message through this node's external request socket

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        try:
            self._manager_address_ledger : dict
            dst_network_config : NetworkConfig = self._manager_address_ledger.get(msg.dst, None)
            if dst_network_config is None:
                raise RuntimeError(f'Could not find network config for simulation element of name {msg.dst}.')

            self.log('parent network config:', dst_network_config)

            dst_address = dst_network_config.get_internal_addresses().get(zmq.REP, None)[-1]
            if '*' in dst_address:
                dst_address : str
                dst_address = dst_address.replace('*', 'localhost')
                    
            if dst_address is None:
                raise RuntimeError(f'Could not find address for simulation element of name {msg.dst}.')
                
            return await self._send_request_message(msg, dst_address, self._manager_socket_map)
        except Exception as e:
            self.log(f'request message to manager failed. {e}')
            raise e

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
                tasks = [asyncio.create_task(self.routine(), name=f'{self.name}_routine'),
                         asyncio.create_task(self.listen(), name=f'{self.name}_listen'),]

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
    async def routine():
        """
        Routine to be performed by the submodule during when the parent module is executing.

        Must have an `asyncio.CancellationError` handler.
        """
        pass

    @abstractmethod
    async def listen(self):
        """
        Listens for messages from the other internal modules.

        Must have an `asyncio.CancellationError` handler.
        """
        pass