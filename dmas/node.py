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
            if not isinstance(InternalModule):
                raise TypeError(f'elements in `modules` argument must be of type `{InternalModule}`. Is of type {type(module)}.')
        
        self.__modules = modules.copy()

    def run(self) -> int:
        """
        Main function. Executes this similation element.

        Procedure follows the sequence:
        1. `activate()`
        2. `execute()`
        3. `deactivate()`.

        Returns `1` if excecuted successfully or if `0` otherwise

        Do NOT override
        """
        async def routine():
            try:
                # initiate successful completion flag
                out = 0

                # activate simulation element
                self._log('activating...', level=logging.INFO)
                await self._activate()

                ## update status to ACTIVATED
                self._status = SimulationElementStatus.ACTIVATED
                self._log('activated! Waiting for simulation to start...', level=logging.INFO)

                # wait for simulatio nstart
                await self._wait_sim_start()
                self._log('simulation has started!', level=logging.INFO)

                ## update status to RUNNING
                self._status = SimulationElementStatus.RUNNING

                ## register simulation runtime start
                self._clock_config.set_simulation_runtime_start( time.perf_counter() )

                # start element life
                self._log('living...', level=logging.INFO)
                await self._execute()
                self._log('living completed!', level=logging.INFO)
                
                self._log('`run()` executed properly.')
                return 1

            finally:
                # deactivate element
                self._log('deactivating...', level=logging.INFO)
                await self._deactivate()
                self._log('deactivation completed!', level=logging.INFO)

                # update status to DEACTIVATED
                self._status = SimulationElementStatus.DEACTIVATED

                #reguster simulation runtime end
                self._clock_config.set_simulation_runtime_end( time.perf_counter() )

        try:
            out = asyncio.run(routine())
            return out

        except Exception as e:
            self._log(f'`run()` interrupted. {e}')
            return 0
        

    async def _activate(self) -> None:
        await super()._activate()

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
        module_names = [f'{self._element_name}/{m.name}' for m in self.__modules]

        while len(responses) < len(self.__modules):
            # listen for messages from internal nodes
            dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
            dst : str; src : str; msg_dict : dict

            if dst not in self.name:
                # received a message intended for someone else. Ignoring message
                continue

            if src not in module_names:
                # received a message from an unrecognized sender. Ignoring message
                continue
            
            msg_type = msg_dict.get('msg_type', None)
            if msg_type != ModuleMessageTypes.SYNC_REQUEST.value:
                # received a message that is not a sync request from an internal module. Ignoring message
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
            msg_type = content['msg_type']

            if (dst not in self.name 
                or SimulationElementRoles.MANAGER.value not in src
                or msg_type != ManagerMessageTypes.RECEPTION_ACK.value):
                
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
            msg_type = content['msg_type']

            if (dst != self.name 
                or src != SimulationElementRoles.MANAGER.value 
                or msg_type != ManagerMessageTypes.SIM_INFO.value):
                
                # undesired message received. Ignoring and trying again later
                await asyncio.wait(random.random())
            else:
                # if the manager did not acknowledge the sync request, try again later
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
            while True:
                # send ready announcement from REQ socket
                msg = NodeReadyMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['msg_type']

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or msg_type != ManagerMessageTypes.RECEPTION_ACK.value
                    ):
                    
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
                msg_type = content['msg_type']

                if (dst not in self.name 
                    or SimulationElementRoles.MANAGER.value not in src 
                    or msg_type != ManagerMessageTypes.SIM_START.value
                    ):
                    
                    # undesired message received. Ignoring and trying again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager did not acknowledge the sync request, try again later
                    return
        try:
            task = asyncio.create_task(subroutine())
            await asyncio.wait_for(task, timeout=10)
            
        except asyncio.TimeoutError as e:
            self._log(f'Wait for simulation start timed out. Aborting. {e}')
            
            # cancel sync subroutine
            task.cancel()
            await task

            raise e


    async def _execute(self) -> None:
        with concurrent.futures.ProcessPoolExecutor(len(self.__modules) + 1) as pool:
            # perform live routine
            pool.submit(asyncio.wait, *[asyncio.create_task(self.__live_routine())])
            
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
        if len(self.__modules) > 0:
            terminate_msg = TerminateInternalModuleMessage(self.name, self.name)
            await self._send_internal_msg(terminate_msg, zmq.PUB)

            responses = []
            module_names = [m.name for m in self.__modules]

            while len(responses) < len(self.__modules):
                # listen for messages from internal nodes
                dst, src, msg_dict = await self._receive_internal_msg(zmq.SUB)
                dst : str; src : str; msg_dict : dict

                if dst not in self.name:
                    # received an internal message intended for someone else. Ignoring message
                    continue

                if src not in module_names:
                    # received an internal message from an unrecognized sender. Ignoring message
                    continue
                
                msg_type = msg_dict.get('msg_type', None)
                if msg_type != ModuleMessageTypes.MODULE_DEACTIVATED.value:
                    # received a message that is not a sync request from an internal module. Ignoring message
                    continue

                if src not in responses:
                    # add to list of synced modules if it hasn't been synched before
                    responses.append(src)

    async def _publish_deactivate(self) -> None:
        try:
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
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    break

            # push deactivate message to monitor
            msg = NodeDeactivatedMessage(self.name)
            dst, src, content = await self._send_external_msg(msg, zmq.PUSH)

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
            send_task = asyncio.create_task( self.__send_msg(msg, zmq.REQ, socket_map) )
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
    