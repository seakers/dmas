import asyncio
import logging
import random
import zmq
from tqdm import tqdm
import concurrent.futures
from dmas.elements import *
from dmas.messages import *
from dmas.modules import InternalModule
from dmas.network import NetworkConfig
from dmas.utils import *

class Node(SimulationElement):
    """
    ## Abstract Simulation Participant 

    Base class for all simulation participants. This including all agents, environment, and simulation manager.
    """
    __doc__ += SimulationElement.__doc__
    def __init__(self, 
                 node_name: str, 
                 node_network_config: NetworkConfig, 
                 manager_network_config : NetworkConfig,
                 modules : list = [], 
                 level: int = logging.INFO, 
                 logger : logging.Logger = None
                 ) -> None:
        super().__init__(node_name, node_network_config, level, logger)   
        self._manager_address_ledger = {SimulationElementRoles.MANAGER.name : manager_network_config}

        if zmq.REQ not in node_network_config.get_manager_addresses():
            raise AttributeError(f'`node_network_config` must contain a REQ port and an address to parent node within external address map.')
        if zmq.SUB not in node_network_config.get_manager_addresses():
            raise AttributeError(f'`node_network_config` must contain a SUB port and an address to parent node within external address map.')
        if zmq.PUSH not in node_network_config.get_manager_addresses():
            raise AttributeError(f'`node_network_config` must contain a PUSH port and an address to parent node within external address map.')

        if len(modules) > 0:
            if zmq.REP not in node_network_config.get_internal_addresses():
                raise AttributeError(f'`node_network_config` must contain a REP port and an address to parent node within internal address map.')
            if zmq.PUB not in node_network_config.get_internal_addresses():
                raise AttributeError(f'`node_network_config` must contain a PUB port and an address to parent node within internal address map.')
        
        self.internal_inbox = None
        self.external_inbox = None

        for module in modules:
            if not isinstance(module, InternalModule):
                raise TypeError(f'elements in `modules` argument must be of type `{InternalModule}`. Is of type {type(module)}.')
        
        self.__modules = modules.copy()
        self.t = None

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

            return 1

        except Exception as e:
            self.log(f'`run()` interrupted. {e}')
            raise e

    async def _activate(self) -> None:
        # give manager time to set up
        self.log('waiting for simulation manager to configure its network...', level=logging.INFO) 
        await asyncio.sleep(1e-1 * random.random())

        # perform activation routine
        await super()._activate()

        # initiate inboxes
        self.internal_inbox = asyncio.Queue()
        self.external_inbox = asyncio.Queue()
    
        # check for correct socket initialization
        if self._internal_socket_map is None:
            raise AttributeError(f'{self.name}: Intra-element communication sockets not activated during activation.')

        if self._internal_address_ledger is None:
            raise RuntimeError(f'{self.name}: Internal address ledger not created during activation.')

    async def _external_sync(self) -> tuple:
        try:
            # request to sync with the simulation manager
            self.log('syncing with simulation manager...', level=logging.INFO) 
            while True:
                # send sync request from REQ socket
                msg = NodeSyncRequestMessage(self.get_element_name(), self._network_config.to_dict())

                dst, src, content = await self.send_manager_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (
                    dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src
                    or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                    ):
                    # if the manager did not acknowledge the sync request, try again later
                    self.log(f'sync request not accepted. trying again later...')
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledged the sync request, stop trying
                    self.log(f'sync request accepted! waiting for simulation information from simulation manager...', level=logging.INFO)
                    break

            # wait for external address ledger from manager
            while True:
                # listen for any incoming broadcasts through PUB socket
                dst, src, content = await self._receive_manager_msg(zmq.SUB)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (
                    dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src
                    or msg_type != ManagerMessageTypes.SIM_INFO.value
                    ):
                    # undesired message received. Ignoring and trying again later
                    self.log(f'received undesired message of type {msg_type}. Ignoring...')
                    await asyncio.wait(random.random())

                else:
                    # if the manager did not acknowledge the sync request, try again later
                    self.log(f'received simulation information message from simulation manager!', level=logging.INFO)
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
        
        except asyncio.CancelledError:
            return
        
    async def _internal_sync(self, clock_config : ClockConfig) -> dict:
        try:
            # wait for module sync request       
            await self.__wait_for_module_sycs()

            # create internal ledger
            internal_address_ledger = dict()
            for module in self.__modules:
                module : InternalModule
                internal_address_ledger[module.name] = module.get_network_config()
            
            # broadcast simulation info to modules
            if self.has_modules():
                msg = NodeInfoMessage(self._element_name, self._element_name, clock_config.to_dict())
                await self._send_internal_msg(msg, zmq.PUB)

            # return ledger
            return internal_address_ledger
        
        except asyncio.CancelledError:
            return
        
    async def __wait_for_module_sycs(self):
        """
        Waits for all internal modules to send their respective sync requests
        """
        await self.__wait_for_module_messages(ModuleMessageTypes.SYNC_REQUEST, 'Syncing w/ Internal Nodes')

    async def _wait_sim_start(self) -> None:
        async def subroutine():
            # wait for all modules to become online
            await self.__wait_for_ready_modules()

            # inform manager that I am ready for the simulation to start
            await self.__broadcast_ready()

            # wait for message from manager
            await self.__wait_for_manager_ready()

            # inform module of simulation start
            if self.has_modules():
                self.log('Informing internal modules of simulation start...')
                sim_start = ActivateInternalModuleMessage(self._element_name, self._element_name)
                await self._send_internal_msg(sim_start, zmq.PUB)

        try:
            task = asyncio.create_task(subroutine())
            await asyncio.wait_for(task, timeout=100)

            self.t = self.get_current_time()
            
        except asyncio.TimeoutError as e:
            self.log(f'Wait for simulation start timed out. Aborting. {e}')
            
            # cancel sync subroutine
            task.cancel()
            await task

            raise e

    @abstractmethod
    async def get_current_time(self) -> float:
        """
        Returns the current simulation time in [s]
        """
        pass
        
    async def __wait_for_ready_modules(self) -> None:
        """
        Waits for all internal modules to become online and be ready to start their simulation
        """
        await self.__wait_for_module_messages(ModuleMessageTypes.MODULE_READY, 'Online Internal Modules')

    async def __broadcast_ready(self):
        """
        Informs the simulation manager that the node is ready to start the simulation.
        """
        self.log('informing manager of ready state...', level=logging.INFO) 
        while True:
            # send ready announcement from REQ socket
            ready_msg = NodeReadyMessage(self.get_element_name())
            dst, src, content = await self.send_manager_message(ready_msg)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if (
                dst not in self.name 
                or SimulationElementRoles.MANAGER.value not in src 
                or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                ):
                # if the manager did not acknowledge the request, try again later
                self.log(f'received undesired message of type {msg_type}. Ignoring...')
                await asyncio.wait(random.random())
            else:
                # if the manager acknowledge the message, stop trying
                self.log(f'ready state message accepted! waiting for simulation to start...', level=logging.INFO)
                break

    async def __wait_for_manager_ready(self):
        """
        Waits for the manager to bradcast a `SIM_START` message
        """
        while True:
            # listen for any incoming broadcasts through SUB socket
            dst, src, content = await self._receive_manager_msg(zmq.SUB)
            dst : str; src : str; content : dict
            msg_type = content['msg_type']

            if (
                dst not in self.name 
                or SimulationElementRoles.MANAGER.value not in src 
                or msg_type != ManagerMessageTypes.SIM_START.value
                ):
                # undesired message received. Ignoring and trying again later
                self.log(f'received undesired message of type {msg_type}. Ignoring...')
                await asyncio.wait(random.random())

            else:
                # manager announced the start of the simulation
                self.log(f'received simulation start message from simulation manager!', level=logging.INFO)
                return

    async def _execute(self) -> None:
        # activate concurrent tasks to be performed by node
        live_task = asyncio.create_task(self.live(), name='live_task')                               # execute live routine
        tasks = [live_task]

        if self.has_modules():
            # listen for modules becoming offline
            offline_modules_task = asyncio.create_task(self.__wait_for_offline_modules())
            tasks.append(offline_modules_task)
        
        # wait until either of the tasts finishes
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

        # cancel all pending tasks
        if live_task in pending:
            live_task.cancel()
            self.log(f'cancelling `{live_task.get_name()}` task...')

        if self.has_modules() and offline_modules_task in pending:
            # internal modules are not yet disabled. inform modules that the node is terminating
            self.log('terminating internal modules....')
            terminate_msg = TerminateInternalModuleMessage(self._element_name, self._element_name)
            await self._send_internal_msg(terminate_msg, zmq.PUB)
        
        # wait for pending tasks to terminate
        self.log(f'waiting on pending tasks to return...')
        await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
        self.log(f'all pending tasks cancelled and terminated!')

    async def live(self) -> None:
        """
        Routine to be performed by simulation node during when the node is executing. 
        
        By default, it only listens for the manager to end the simulation but may be overriden
        to extend functionality.

        Must be able to handle `asyncio.CancelledError` exceptions.
        """
        try:
            self.log(f'waiting for manager to end simulation...')
            while True:
                dst, src, content = await self._receive_manager_msg(zmq.SUB)
                self.log(f'message received: {content}', level=logging.DEBUG)

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                    self.log('wrong message received. ignoring message...')
                else:
                    self.log('simulation end message received! ending simulation...')
                    break

        except asyncio.CancelledError:
            self.log(f'`live()` interrupted.')
            return
        except Exception as e:
            self.log(f'`live()` failed. {e}')
            raise e

    async def __wait_for_offline_modules(self) -> None:
        """
        Waits for all internal modules to become offline
        """
        await self.__wait_for_module_messages(ModuleMessageTypes.MODULE_DEACTIVATED, 'Offline Internal Modules')

    async def __wait_for_module_messages(self, target_type : ModuleMessageTypes, desc : str):
        """
        Waits for all internal modules to send a message of type `target_type` through the node's REP port
        """
        responses = []
        module_names = [m.name for m in self.__modules]

        with tqdm(total=len(self.__modules) , desc=f'{self.name}: {desc}') as pbar:
            while len(responses) < len(self.__modules):
                # listen for messages from internal module
                dst, src, msg_dict = await self._receive_internal_msg(zmq.REP)
                dst : str; src : str; msg_dict : dict
                msg_type = msg_dict.get('msg_type', None)

                if (dst in self.name
                    and src in module_names
                    and msg_type == target_type.value
                    and src not in responses
                    ):
                    # Add to list of registered modules if it hasn't been registered before
                    responses.append(src)
                    pbar.update(1)
                    resp = NodeReceptionAckMessage(self._element_name, src)
                else:
                    # ignore message
                    resp = NodeReceptionIgnoredMessage(self._element_name, src)

                # respond to module
                await self._send_internal_msg(resp, zmq.REP)

    async def _publish_deactivate(self) -> None:
        try:
            # inform monitor that I am deactivated
            self.log(f'informing monitor of offline status...')
            msg = NodeDeactivatedMessage(self.name)
            await self._send_manager_msg(msg, zmq.PUSH)
            self.log(f'informed monitor of offline status. informing manager of offline status...')

            # inform manager that I am deactivated
            while True:
                # send ready announcement from REQ socket
                msg = NodeDeactivatedMessage(self.name)
                dst, src, content = await self.send_manager_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src
                    or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                    ):
                    # if the manager did not acknowledge the request, try again later
                    self.log(f'manager did not accept my message. trying again...')
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    self.log(f'manager accepted my message! informing monitor of offline status....')
                    break

        except asyncio.CancelledError:
            return

    def has_modules(self) -> bool:
        """
        checks if this node has any internal modules
        """
        return len(self.__modules) > 0

    async def send_peer_message(self, msg : SimulationMessage) -> tuple:
        """
        Sends a peer-to-peer message and returns the destination's response

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)

        ### Usage:
            `dst, src, msg_dict = await self.send_peer_message(msg)`
        """
        try:
            return await self._send_external_request_message(msg)
        except asyncio.CancelledError:
            return

    async def listen_peer_message(self) -> tuple:
        """
        Listens for any incoming peer-to-peer message

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)

        ### Usage:
            `dst, src, msg_dict = await self.listen_peer_message(msg)`
        """
        try:
            return await self._receive_external_msg(zmq.REP)
        except asyncio.CancelledError:
            return

    async def respond_peer_message(self, resp : SimulationMessage) -> None:
        """
        Responds to any incoming peer-to-peer message

        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        try:
            return await self._send_external_msg(resp, zmq.REP)
        except asyncio.CancelledError:
            return

    async def send_peer_broadcast(self, msg : SimulationMessage) -> None:
        """
        Broadcasts message to all peers currently connected to this network node

        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        try:
            return await self._send_external_msg(msg, zmq.PUB)
        except asyncio.CancelledError:
            return
    
    async def listen_peer_broadcast(self) -> tuple:
        """
        Listens for any broadcast messages from every peer that this network node is connected to

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)

        ### Usage:
            `dst, src, msg_dict = await self.listen_peer_broadcast(msg)`
        """
        try:
            return await self._receive_external_msg(zmq.SUB)
        except asyncio.CancelledError:
            return
    
    async def listen_manager_broadcast(self) -> tuple:
        """
        Listens for any broadcast messages from the simulation manager that this network node is connected to

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)

        ### Usage:
            `dst, src, msg_dict = await self.listen_manager_broadcast(msg)`
        """
        try:
            return await self._receive_manager_msg(zmq.SUB)
        except asyncio.CancelledError:
            return

    async def subscribe_to_broadcasts(self, dst : str) -> None:
        """
        Connects this network node's subscribe port to the destination's publish port
        """
        # get the destination's publish port 
        dst_network_config : NetworkConfig = self._external_address_ledger.get(dst, None)
        if dst_network_config is None: 
            raise 
            
        dst_addresses = dst_network_config.get_external_addresses().get(zmq.PUB, None)
        if dst_addresses is None or len(dst_addresses) < 1:
            pass
        dst_address = dst_addresses[-1]
        
        # get own sub port
        socket, _ = self._external_socket_map.get(zmq.SUB)
        socket : zmq.Socket

        # conenct to destiation
        socket.connect(dst_address)

    async def unsubscribe_to_broadcasts(self, dst) -> None:
        """
        Disconnects this network node's subscribe port to the destination's publish port
        """
        # get the destination's publish port 
        dst_network_config : NetworkConfig = self._external_address_ledger.get(dst, None)
        if dst_network_config is None: 
            raise 
            
        dst_addresses = dst_network_config.get_external_addresses().get(zmq.PUB, None)
        if dst_addresses is None or len(dst_addresses) < 1:
            pass
        dst_address = dst_addresses[-1]
        
        # get own sub port
        socket, _ = self._external_socket_map.get(zmq.SUB)
        socket : zmq.Socket

        # conenct to destiation
        socket.disconnect(dst_address)