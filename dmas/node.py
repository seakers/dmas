
import asyncio
import logging
import random
import zmq
import concurrent.futures
from dmas.element import SimulationElement
from dmas.messages import *
from dmas.modules import InternalModule
from dmas.utils import *

class Node(SimulationElement):
    """
    ## Abstract Simulation Participant 

    Base class for all simulation participants. This including all agents, environment, and simulation manager.


    ### Communications diagram:
    +-----------+---------+       +--------------+
    |           | REQ     |------>|              | 
    |           +---------+       |              |
    | ABSTRACT  | PUB     |------>| SIM ELEMENTS |
    |   SIM     +---------+       |              |
    |   NODE    | SUB     |<------|              |
    |           +---------+       +==============+ 
    |           | PUSH    |------>|  SIM MONITOR |
    +-----------+---------+       +--------------+
    
    """
    __doc__ += SimulationElement.__doc__
    def __init__(self, name: str, network_config: NetworkConfig, modules : list = [], level: int = logging.INFO) -> None:
        super().__init__(name, network_config, level)   
        
        for module in modules:
            if not isinstance(InternalModule):
                raise TypeError(f'elements in `modules` argument must be of type `{InternalModule}`. Is of type {type(module)}.')
        
        self.__modules = modules.copy()

    def _activate(self) -> None:
        super()._activate()

        # check for correct socket initialization
        if self._internal_socket_map is None:
            raise AttributeError(f'{self.name}: Intra-element communication sockets not activated during activation.')

        if self._internal_address_ledger is None:
            raise RuntimeError(f'{self.name}: Internal address ledger not created during activation.')

    def config_network(self) -> tuple:
        # configure own network ports
        external_socket_map, internal_socket_map = super().config_network()

        # instruct internal modules to configure their own network ports
        if len(self.__modules) > 0:
            with concurrent.futures.ThreadPoolExecutor(len(self.__modules)) as pool:
                for module in self.__modules:
                    module : InternalModule
                    pool.submit(module.config_network, *[])

        return external_socket_map, internal_socket_map

    async def _internal_sync(self) -> dict:
        # instruct internal modules to sync their networks with me
        with concurrent.futures.ThreadPoolExecutor(len(self.__modules) + 1) as pool:
            pool.submit(asyncio.run, *[self.__wait_for_online_modules()])    

            for module in self.__modules:
                module : InternalModule
                pool.submit(module.sync, *[])                       

        # create internal ledger
        internal_address_ledger = dict()
        for module in self.__modules:
            module : InternalModule
            internal_address_ledger[module.name] = module.get_network_config()

        # return ledger
        return internal_address_ledger
    
    async def __wait_for_online_modules(self) -> None:
        """
        Waits for all internal modules to become online
        """
        responses = []
        module_names = [m.name for m in self.__modules]

        while len(responses) < len(self.__modules):
            # listen for messages from internal nodes
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict

            if dst != self.name:
                # received a message intended for someone else. Ignoring message
                continue

            if src not in module_names:
                # received a message from an unrecognized sender. Ignoring message
                continue
            
            msg_type = msg_dict.get('@type', None)
            if msg_type is not None and ModuleMessageTypes[msg_type] != ModuleMessageTypes.SYNC_REQUEST:
                # eceived a message that is not a sync request from an internal module. Ignoring message
                continue

            if src not in responses:
                # Add to list of synced modules if it hasn't been synched before
                responses.append(src)

        # inform all internal nodes that they are now synched with their parent simulation node
        synced_msg = NodeReceptionAckMessage(self.name, self.name)
        await self._send_internal_msg(synced_msg, zmq.PUB)

    async def _external_sync(self):
        # request to sync with the simulation manager
        while True:
            # send sync request from REQ socket
            msg = NodeSyncRequestMessage(self.name, self._network_config)
            dst, src, content = await self._send_external_request_message(msg)
            dst : str; src : str; content : dict
            msg_type = content['@type']

            if (dst != self.name 
                or src != SimulationElementRoles.MANAGER.value 
                or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                
                # if the manager did not acknowledge the sync request, try again later
                await asyncio.wait(random.random())
            else:
                # if the manager acknowledged the sync request, stop trying
                break

        # wait for external address ledger from manager
        while True:
            # listen for any incoming broadcasts through PUB socket
            dst, src, content = await self._receive_external_msg(zmq.SUB)
            dst : str; src : str; content : dict
            msg_type = content['@type']

            if (dst != self.name 
                or src != SimulationElementRoles.MANAGER.value 
                or ManagerMessageTypes[msg_type] != ManagerMessageTypes.SIM_INFO):
                
                # undesired message received. Ignoring and trying again later
                await asyncio.wait(random.random())
            else:
                # if the manager did not acknowledge the sync request, try again later
                msg : SimulationInfoMessage = SimulationInfoMessage.from_dict(content)
                return msg.get_address_ledger()

    def _wait_sim_start(self) -> None:
        async def subroutine():
            # inform manager that I am ready for the simulation to start
            while True:
                # send ready announcement from REQ socket
                msg = NodeReadyMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                    
                    # if the manager did not acknowledge the request, try again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    break

            # wait for message from manager
            while True:
                # listen for any incoming broadcasts through PUB socket
                dst, src, content = await self._receive_external_msg(zmq.SUB)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.SIM_START):
                    
                    # undesired message received. Ignoring and trying again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager did not acknowledge the sync request, try again later
                    return

        async def routine():
            try:
                task = asyncio.create_task(subroutine())
                await asyncio.wait_for(task, timeout=10)
                
            except asyncio.TimeoutError as e:
                self._log(f'Wait for simulation start timed out. Aborting. {e}')
                
                # cancel sync subroutine
                task.cancel()
                await task

                raise e

        return (asyncio.run(routine()))

    def _execute(self) -> None:
        with concurrent.futures.ProcessPoolExecutor(len(self.__modules) + 1) as pool:
            # perform live routine
            pool.submit(asyncio.run, *[self.__live_routine()])
            
            # start all modules' run routines
            for module in self.__modules:
                module : InternalModule
                pool.submit(module.run, *[])

    async def __live_routine(self):
        """
        Wrapper method for node's `live` method. 

        This method terminates all internal modules' processes after their parent node fulfills
        its `live` routine.
        """
        try:
            await self._live()
        finally:
            # await for confirmation from modules
            await self.__wait_for_offline_modules()

    @abstractmethod
    async def _live(self) -> None:
        """
        Routine to be performed by simulation node during when the node is executing
        """
        pass

    async def __wait_for_offline_modules(self) -> None:
        """
        Waits for all internal modules to become offline
        """
        # send terminate message to all modules
        terminate_msg = TerminateInternalModuleMessage(self.name, self.name)
        await self._send_internal_msg(terminate_msg, zmq.PUB)

        responses = []
        module_names = [m.name for m in self.__modules]

        while len(responses) < len(self.__modules):
            # listen for messages from internal nodes
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict

            if dst != self.name:
                # received an internal message intended for someone else. Ignoring message
                continue

            if src not in module_names:
                # received an internal message from an unrecognized sender. Ignoring message
                continue
            
            msg_type = msg_dict.get('@type', None)
            if msg_type is not None and ModuleMessageTypes[msg_type] != ModuleMessageTypes.MODULE_DEACTIVATED:
                # received a message that is not a sync request from an internal module. Ignoring message
                continue

            if src not in responses:
                # add to list of synced modules if it hasn't been synched before
                responses.append(src)

    def _publish_deactivate(self) -> None:
        async def routine():
            # inform manager that I am deactivated
            while True:
                # send ready announcement from REQ socket
                msg = NodeDeactivatedMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                    
                    # if the manager did not acknowledge the request, try again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    break

            # push deactivate message to monitor
            msg = NodeDeactivatedMessage(self.name)
            dst, src, content = await self._send_external_msg(msg, zmq.PUSH)

        return asyncio.run(routine())

    async def _send_request_message(self, msg : SimulationMessage, address_ledger : dict, socket_map : dict) -> list:
        """
        Sends a message through one of this node's request socket

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - address_ledger (`dict`): address ledger containing the destinations address
            - socket_map (`dict`): list mapping de the desired type of socket to a socket contained by the node

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        try:
            # initialize progress trackers
            send_task = None
            receive_task = None

            # get destination's socket address
            dst_network_config : NetworkConfig = address_ledger.get(msg.get_dst(), None)
            dst_address = dst_network_config.get_external_addresses().get(zmq.REP, None)
            
            if dst_address is None:
                raise RuntimeError(f'Could not find address for simulation element of name {msg.get_dst()}.')
            
            # connect to destination's socket
            socket, _ = socket_map.get(zmq.REQ, (None, None))
            socket : zmq.Socket
            self._log(f'connecting to {msg.get_dst()} via `{dst_address}`...')
            socket.connect(dst_address)
            self._log(f'connection to {msg.get_dst()} established! Transmitting a message of type {type(msg)}...')

            # transmit message
            send_task = asyncio.create_task( self.__send_msg(msg, zmq.REQ, socket_map) )
            await send_task
            self._log(f'message of type {type(msg)} transmitted sucessfully! Waiting for response from {msg.get_dst()}...')

            # wait for response
            receive_task = asyncio.create_task( self._receive_external_msg(zmq.REQ) )
            await receive_task
            self._log(f'response received from {msg.get_dst()}!')

            # disconnect from destination's socket
            socket.disconnect(dst_address)

            return receive_task.result()
        
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            if send_task is not None and not send_task.done():
                send_task.cancel()
                await send_task
            
            if receive_task is not None and not receive_task.done():
                receive_task.cancel()
                await receive_task

        except Exception as e:
            self._log(f'message broadcast failed.')
            raise e

    async def _send_external_request_message(self, msg : SimulationMessage) -> list:
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
        return await self._send_request_message(msg, self._external_address_ledger, self._external_socket_map)
    