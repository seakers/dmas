import asyncio
import logging
import random
import zmq
import concurrent.futures
from dmas.element import *
from dmas.messages import *
from dmas.modules import InternalModule
from dmas.network import NetworkConfig
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
    def __init__(self, name: str, network_config: NetworkConfig, modules : list = [], level: int = logging.INFO, logger : logging.Logger = None) -> None:
        super().__init__(name, network_config, level, logger)   
        
        for module in modules:
            if not isinstance(module, InternalModule):
                raise TypeError(f'elements in `modules` argument must be of type `{InternalModule}`. Is of type {type(module)}.')
        
        self.__modules = modules.copy()

    def run(self) -> int:
        """
        Main function. Executes this similation element along with its submodules.

        Returns `1` if excecuted successfully or if `0` otherwise
        """
        try:
            with concurrent.futures.ThreadPoolExecutor(len(self.__modules) + 1) as pool:
                pool.submit(asyncio.run, *[self._run_routine()])
                for module in self.__modules:
                    module : InternalModule
                    pool.submit(module.run, *[])

        except Exception as e:
            self._log(f'`run()` interrupted. {e}')
            raise e

    async def _activate(self) -> None:
        await super()._activate()

        # check for correct socket initialization
        if self._internal_socket_map is None:
            raise AttributeError(f'{self.name}: Intra-element communication sockets not activated during activation.')

        if self._internal_address_ledger is None:
            raise RuntimeError(f'{self.name}: Internal address ledger not created during activation.')
    
    async def _internal_sync(self) -> dict:
        # wait for all modules to be online
        await self.__wait_for_online_modules()

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

        #TODO ADD REQ-REP PORT TO INTERNAL MODULES AND NODES FOR SYNCING

        responses = []
        module_names = [f'{self._element_name}/{m.name}' for m in self.__modules]

        if len(self.__modules) > 0:
            self._log('waiting for internal nodes to become online...')
            while len(responses) < len(self.__modules):
                # listen for messages from internal nodes
                dst, src, msg_dict = await self._receive_internal_msg(zmq.REP)
                dst : str; src : str; msg_dict : dict
                msg_type = msg_dict.get('msg_type', None)

                if (dst not in self.name
                    or src not in module_names
                    or msg_type != ModuleMessageTypes.SYNC_REQUEST.value
                    ):
                    resp = NodeReceptionAckMessage(self.name, src)
                    await self._send
                    continue

                if src not in responses:
                    # Add to list of synced modules if it hasn't been synched before
                    responses.append(src)

            self._log('all internal nodes are now online! Informing them that they are now synced with their parent node...')
            # inform all internal nodes that they are now synched with their parent simulation node
            synced_msg = NodeReceptionAckMessage(self._element_name, self._element_name)
            await self._send_internal_msg(synced_msg, zmq.PUB)

    async def _external_sync(self):
        # request to sync with the simulation manager
        self._log('syncing with simulation manager...', level=logging.INFO) 
        while True:
            # send sync request from REQ socket
            msg = NodeSyncRequestMessage(self.name, self._network_config.to_dict())
            dst, src, content = await self._send_external_request_message(msg)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if (
                dst not in self.name 
                or SimulationElementRoles.MANAGER.value not in src
                or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                ):
                # if the manager did not acknowledge the sync request, try again later
                self._log(f'sync request not accepted. trying again later...')
                await asyncio.wait(random.random())
            else:
                # if the manager acknowledged the sync request, stop trying
                self._log(f'sync request accepted! waiting for simulation information from simulation manager...', level=logging.INFO)
                break

        # wait for external address ledger from manager
        while True:
            # listen for any incoming broadcasts through PUB socket
            dst, src, content = await self._receive_external_msg(zmq.SUB)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if (
                dst not in self.name 
                or SimulationElementRoles.MANAGER.value not in src
                or msg_type != ManagerMessageTypes.SIM_INFO.value
                ):
                # undesired message received. Ignoring and trying again later
                self._log(f'received undesired message of type {msg_type}. Ignoring...')
                await asyncio.wait(random.random())
            else:
                # if the manager did not acknowledge the sync request, try again later
                self._log(f'received simulation information message from simulation manager!', level=logging.INFO)
                msg = SimulationInfoMessage(**content)
                
                external_ledger = dict()
                ledger_dicts : dict = msg.get_address_ledger()
                for node in ledger_dicts:
                    external_ledger[node] = NetworkConfig(**ledger_dicts[node])

                clock_config = msg.get_clock_info()
                clock_type = clock_config['clock_type']
                if clock_type == ClockTypes.REAL_TIME.value:
                    return RealTimeClockConfig(**clock_config), external_ledger
                    
                elif clock_type == ClockTypes.ACCELERATED_REAL_TIME.value:
                    return AcceleratedRealTimeClockConfig(**clock_config), external_ledger

                else:
                    raise NotImplementedError(f'clock type {clock_type} not yet implemented.')

    async def _wait_sim_start(self) -> None:
        async def subroutine():
            # inform manager that I am ready for the simulation to start
            self._log('informing manager of ready state...', level=logging.INFO) 
            while True:
                # send ready announcement from REQ socket
                msg = NodeReadyMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (
                    dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                    ):
                    # if the manager did not acknowledge the request, try again later
                    self._log(f'received undesired message of type {msg_type}. Ignoring...')
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    self._log(f'ready state message accepted! waiting for simulation to start...', level=logging.INFO)
                    break

            # wait for message from manager
            while True:
                # listen for any incoming broadcasts through PUB socket
                dst, src, content = await self._receive_external_msg(zmq.SUB)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (
                    dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or msg_type != ManagerMessageTypes.SIM_START.value
                    ):
                    # undesired message received. Ignoring and trying again later
                    self._log(f'received undesired message of type {msg_type}. Ignoring...')
                    await asyncio.wait(random.random())

                else:
                    # manager announced the start of the simulation
                    self._log(f'received simulation start message from simulation manager!', level=logging.INFO)
                    return
        try:
            task = asyncio.create_task(subroutine())
            await asyncio.wait_for(task, timeout=100)
            
        except asyncio.TimeoutError as e:
            self._log(f'Wait for simulation start timed out. Aborting. {e}')
            
            # cancel sync subroutine
            task.cancel()
            await task

            raise e

    async def _execute(self) -> None:
        live_task = asyncio.create_task(self._live())
        if len(self.__modules) > 0:
            offline_nodes_task = asyncio.create_task(self.__wait_for_offline_modules())

            _, pending = await asyncio.wait([live_task, offline_nodes_task], return_when=asyncio.FIRST_COMPLETED)
            pending : list

            if live_task in pending:
                live_task.cancel()
            else:
                # node is disabled. inform modules that the node is terminating
                self._log('node\'s `live()` finalized. Terminating internal modules....')
                terminate_msg = TerminateInternalModuleMessage(self.name, self.name)
                await self._send_internal_msg(terminate_msg, zmq.PUB)

                # wait for all modules to terminate and become offline
                terminate_task = asyncio.create_task(self.__wait_for_offline_modules())
                pending.append(terminate_task)

            await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)               
        else:
            await live_task

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
        responses = []
        module_names = [m.name for m in self.__modules]

        self._log('listening for internal modules\' termination confirmation...')
        while len(responses) < len(self.__modules):
            # listen for messages from internal nodes
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict
            msg_type = msg_dict.get('msg_type', None)    

            if (
                dst not in self.name
                or src not in module_names 
                or msg_type != ModuleMessageTypes.MODULE_DEACTIVATED.value
                ):
                # undesired message received. Ignoring and trying again later
                self._log(f'received undesired message of type {msg_type}. Ignoring...')
                continue

            if src not in responses:
                # add to list of offline modules if it hasn't been registered as offline before
                self._log(f'{src} is now offline! offline module status: {len(responses)}/{len(self.__modules)}')
                responses.append(src)

    async def _publish_deactivate(self) -> None:
        try:
            # inform monitor that I am deactivated
            self._log(f'informing monitor of offline status...')
            msg = NodeDeactivatedMessage(self.name)
            await self._send_external_msg(msg, zmq.PUSH)
            self._log(f'informed monitor of offline status. informing manager of offline status...')

            # inform manager that I am deactivated
            while True:
                # send ready announcement from REQ socket
                msg = NodeDeactivatedMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src
                    or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                    ):
                    # if the manager did not acknowledge the request, try again later
                    self._log(f'manager did not accept my message. trying again...')
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    self._log(f'manager accepted my message! informing monitor of offline status....')
                    break

        except asyncio.CancelledError:
            return

    async def __send_request_message(self, msg : SimulationMessage, address_ledger : dict, socket_map : dict) -> list:
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
            if SimulationElementRoles.MANAGER.value in msg.dst:
                dst_addresses = self._network_config.get_external_addresses().get(zmq.REQ)
                dst_address = dst_addresses[-1]
            else:
                dst_network_config : NetworkConfig = address_ledger.get(msg.dst, None)
                dst_address = dst_network_config.get_external_addresses().get(zmq.REP, None)
            
            if dst_address is None:
                raise RuntimeError(f'Could not find address for simulation element of name {msg.dst}.')
            
            # connect to destination's socket
            socket, _ = socket_map.get(zmq.REQ, (None, None))
            socket : zmq.Socket
            self._log(f'connecting to {msg.dst} via `{dst_address}`...')
            socket.connect(dst_address)
            self._log(f'connection to {msg.dst} established! Transmitting a message of type {type(msg)}...')

            # transmit message
            send_task = asyncio.create_task( self._send_msg(msg, zmq.REQ, socket_map) )
            await send_task
            self._log(f'message of type {type(msg)} transmitted sucessfully! Waiting for response from {msg.dst}...')

            # wait for response
            receive_task = asyncio.create_task( self._receive_external_msg(zmq.REQ) )
            await receive_task
            self._log(f'response received from {msg.dst}!')

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
        return await self.__send_request_message(msg, self._external_address_ledger, self._external_socket_map)
    