from abc import ABC, abstractmethod
from beartype import beartype
import asyncio
import datetime
import logging
import time
import zmq

from dmas.messages import *
from dmas.utils import *
from dmas.element import SimulationElement

class AbstractManager(SimulationElement):
    """
    ## Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Attributes:
        - _name (`str`): The name of this simulation manager
        - _network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
        - _my_addresses (`list`): List of addresses used by this simulation manager

        - _rep_socket (:obj:`Socket`): The manager's response port socket
        - _rep_socket_lock (:obj:`Lock`): async lock for _rep_socket (:obj:`socket`)
        - _pub_socket (:obj:`Socket`): The manager's broadcast port socket
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket (:obj:`Socket`): The manager's monitor port socket        
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)

        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
        - _address_ledger (`dict`): ledger containing the addresses pointing to each node's connecting ports

    ### Communications diagram:
    +------------+---------+                
    |            | REP     |<---->>
    | SIMULATION +---------+       
    |   MANAGER  | PUB     |------>
    |            +---------+       
    |            | PUSH    |------>
    +------------+---------+             
    """
    @beartype
    def __init__(self, 
            simulation_element_name_list : list,
            network_config : ManagerNetworkConfig,
            clock_config : ClockConfig,
            level : int = logging.INFO
            ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of the names of all simulation elements
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
            - level (`int`): logging level for this simulation element
        """
        super().__init__(SimulationElementTypes.MANAGER.name, network_config, level)

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._offline_simulation_element_list = []
        self._clock_config = clock_config
        
        # if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
        #     raise RuntimeError('List of simulation elements must include the simulation environment.')

        # TODO check if there is more than one environment in the list 

    async def _activate(self) -> None:
        # initialzie network sockets
        await super()._activate()

        # sync with all simulation elements
        self._log('syncing simulation elements...', level=logging.INFO)
        await self._sync()
        self._log('sync complete!', level=logging.INFO)

        # announce sim start
        self._log('broadcasting simulation start...', level=logging.INFO)
        await self._broadcast_sim_start()
        self._log('simlation started!', level=logging.INFO)

    async def _config_network(self) -> list:
        """
        Initializes and connects essential network port sockets for a simulation manager. 
        
        #### Sockets Initialized:
            - _rep_socket (:obj:`Socket`): The manager's response port socket
            - _pub_socket (:obj:`Socket`): The manager's broadcast port socket
            - _monitor_push_socket (:obj:`Socket`): The manager's monitor port socket

        #### Returns:
            - port_list (`list`): contains all sockets used by this simulation element
        """
        port_list : list = await super()._config_network()

        # direct message response port
        self._rep_socket = self._context.socket(zmq.REP)
        self._network_config : ManagerNetworkConfig

        peer_in_address : str = self._network_config.get_response_address()
        self._rep_socket.bind(peer_in_address)
        self._rep_socket.setsockopt(zmq.LINGER, 0)
        self._rep_socket_lock = asyncio.Lock()

        port_list.append(self._rep_socket)

        return port_list

    async def _sync(self) -> None:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and become online. 
        
        Elements will then reach out to the manager through its `_peer_in_socket` socket and subscribe to future broadcasts 
        from the manager's `_pub_socket` socket.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports
        and broadcast it to all memebers of the simulation. 
        """
        await self._rep_socket_lock.acquire()

        while len(self._address_ledger) < len(self._simulation_element_name_list):
            if len(self._simulation_element_name_list) == 0:
                break 
            
            # wait for incoming messages
            src, msg_dict = await self._receive_from_socket(self._rep_socket, self._rep_socket_lock)
            msg_type = msg_dict['@type']
            
            if NodeMessageTypes[msg_type] != NodeMessageTypes.SYNC_REQUEST:
                # ignore all incoming messages that are not Sync Requests
                response = dict()
                response['@type'] = 'IGNORED'

                src : str
                response_str : str = str(json.dumps(response))
                await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])


            # unpack and sync message
            sync_req = SyncRequestMessage.from_dict(msg_dict)

            self._log(f'Received sync request from node {sync_req.get_src()}!')

            # log subscriber confirmatoin
            if src in self._simulation_element_name_list:
                if src not in self._address_ledger:
                    # node is a part of the simulation and has not yet been synchronized

                    # add node to network information to address map
                    self._address_ledger[src] = sync_req.get_network_config()
                    self._log(f'Node {sync_req.get_src()} is now synchronized! Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
                else:
                    # node is a part of the simulation but has already been synchronized
                    self._log(f'Node {sync_req.get_src()} is already synchronized to the simulation manager. Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            else:
                # node is not a part of the simulation
                self._log(f'Node {sync_req.get_src()} is not part of this simulation. Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            
            # send synchronization acknowledgement
            response = dict()
            response['@type'] = 'ACK'

            src : str
            response_str : str = str(json.dumps(response))
            await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])

        self._rep_socket_lock.release()
        self._log(f'sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})! Broadcasting sync info...', level=logging.INFO)

        # broadcast simulation information message
        sim_info_msg = SimulationInfoMessage(self._address_ledger, self._clock_config, time.perf_counter())
        await self._broadcast_message(sim_info_msg)

    async def _broadcast_sim_start(self) -> None:
        """
        Broadcasts this manager's simulation element address ledger to all subscribed elements to signal the start of the simulation.
        """
        await self._rep_socket_lock.acquire()

        # wait for every simulation node to be ready
        elements_ready = []
        while len(elements_ready) < len(self._simulation_element_name_list):
            if len(self._simulation_element_name_list) == 0:
                break 

            # wait for incoming messages
            src, msg_dict = await self._receive_from_socket(self._rep_socket, self._rep_socket_lock)
            msg_type = msg_dict['@type']
            
            if NodeMessageTypes[msg_type] != NodeMessageTypes.NODE_READY:
                # ignore all incoming messages that are not Ready Status messages
                response = dict()
                response['@type'] = 'IGNORED'

                src : str
                response_str : str = str(json.dumps(response))
                await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])

                continue

            # unpack and node ready message
            ready_msg = NodeReadyMessage.from_dict(msg_dict)

            logging.debug(f'Received ready message from node {ready_msg.get_src()}!')

            # log subscriber confirmation
            if src in self._simulation_element_name_list:
                if src not in elements_ready:
                    # node is a part of the simulation, is ready, and has not yet been registered

                    # add node to list of ready nodes
                    elements_ready.append(src)       
                    logging.debug(f'Node {src} is now regsitered as READY! Simulation ready status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')             
                else:
                    # node is a part of the simulation but has already been synchronized
                    logging.debug(f'Node {src} is already regsitered as ready for the simulation manager. simulation ready status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            else:
                # node is not a part of the simulation
                logging.debug(f'Node {src} is not part of this simulation. Simulation ready status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            
            # send acknowledgement
            response = dict()
            response['@type'] = 'ACK'

            src : str
            response_str : str = str(json.dumps(response))
            await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])
        
        self._rep_socket_lock.release()
        self._log(f'simulation ready status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})! Broadcasting simlation start...', level=logging.INFO)

        # broadcast sim start  message
        sim_start_msg = SimulationStartMessage(time.perf_counter())
        await self._broadcast_message(sim_start_msg)

    async def _wait_for_offline_confirmations(self) -> None:
        """
        Listens for any incoming messages from other simulation elements. Counts how many simulation elements are offline.

        Returns when all simulation elements are offline.
        """
        try:
            await self._rep_socket_lock.acquire()
            
            while len(self._offline_simulation_element_list) < len(self._simulation_element_name_list):
                # wait for any incoming messages
                src, msg_dict = await self._receive_from_socket(self._rep_socket, self._rep_socket_lock)
                msg_type = msg_dict['@type']

                if NodeMessageTypes[msg_type] != NodeMessageTypes.NODE_DEACTIVATED:
                    # ignore all incoming messages that are not of type Node Deactivated
                    response = dict()
                    response['@type'] = 'IGNORED'

                    src : str
                    response_str : str = str(json.dumps(response))
                    await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])

                    continue

                # unpack and sync message
                deactivated_message = NodeDeactivatedMessage.from_dict(msg_dict)

                self._log(f'Received node deactivated message from node {deactivated_message.get_src()}!')

                if src in self._simulation_element_name_list:
                    if src not in self._offline_simulation_element_list:
                        # node is a part of the simulation, is now offline, and has not yet been registered

                        # add to offline element list 
                        self._offline_simulation_element_list.append(src)
                        logging.debug(f'Node {src} is now regsitered as OFFLINE! Offline simulation elements: ({len(self._offline_simulation_element_list)}/{len(self._simulation_element_name_list)})')             
                    else:
                        # node is a part of the simulation but has already been synchronized
                        logging.debug(f'Node {src} is already regsitered as offline in this simulation. Offline simulation elements: ({len(self._offline_simulation_element_list)}/{len(self._simulation_element_name_list)})')
                else:
                    # node is not a part of the simulation
                    logging.debug(f'Node {src} is not part of this simulation. Offline simulation elements: ({len(self._offline_simulation_element_list)}/{len(self._simulation_element_name_list)})')

                # send synchronization acknowledgement
                response = dict()
                response['@type'] = 'ACK'

                src : str
                response_str : str = str(json.dumps(response))
                await self._rep_socket.send_multipart([src.encode('ascii'), response_str.encode('ascii')])
            
            self._log('all elements of the simulation are offline.')
            
        except asyncio.CancelledError:
            if self._rep_socket_lock.locked():
                self._rep_socket_lock.release()
        finally:
            if self._rep_socket_lock.locked():
                self._rep_socket_lock.release()

    async def _listen(self):
        try:
            wait_for_offline_task = None
            wait_for_offline_task = asyncio.create_task(self._wait_for_offline_confirmations())
            await wait_for_offline_task

        except asyncio.CancelledError:
            if wait_for_offline_task is not None:
                wait_for_offline_task : asyncio.Task
                wait_for_offline_task.cancel()
                await wait_for_offline_task

    async def _live(self):
        try:
            # wait for simulation duration to pass
            self._clock_config : ClockConfig
            delta = self._clock_config.end_date - self._clock_config.start_date

            await self._sim_wait(delta.seconds)

        except asyncio.CancelledError:
            return

    async def _shut_down(self) -> None:
        # broadcast sim end message
        await self._broadcast_message( SimulationEndMessage(time.perf_counter()) )

        # wait for confirmation from all simulation elements
        await self._wait_for_offline_confirmations()

        # TODO send monitor sim end message 
        
        # close all communication ports
        return await super()._shut_down()

class RealTimeSimulationManager(AbstractManager):
    """
    ## Real Time Simulation Manager Class 
    
    Regulates the start and end of a simulation. Runs a clock in real time.

    ### Attributes:
        - _name (`str`): The name of this simulation manager
        - _network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
        - _my_addresses (`list`): List of addresses used by this simulation manager

        - _rep_socket (:obj:`Socket`): The manager's response port socket
        - _rep_socket_lock (:obj:`Lock`): async lock for _rep_socket (:obj:`socket`)
        - _pub_socket (:obj:`Socket`): The manager's broadcast port socket
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket (:obj:`Socket`): The manager's monitor port socket        
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)

        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`RealTimeClockConfig`): description of this simulation's clock configuration
        - _address_ledger (`dict`): ledger containing the addresses pointing to each node's connecting ports

    ### Communications diagram:
    +------------+---------+                
    |            | REP     |<---->>
    | SIMULATION +---------+       
    |   MANAGER  | PUB     |------>
    |            +---------+       
    |            | PUSH    |------>
    +------------+---------+           
    """
    @beartype
    def __init__(self, 
                simulation_element_name_list: list, 
                network_config: ManagerNetworkConfig, 
                clock_config: RealTimeClockConfig,
                level:int = logging.INFO
                ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of the names of all simulation elements
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - clock_config (:obj:`RealTimeClockConfig`): description of this simulation's clock configuration
            - level (`int`): logging level for this simulation element
        """
        super().__init__(simulation_element_name_list, network_config, clock_config, level)

    # async def _live(self):
    #     try:
    #         # wait for simulation duration to pass
    #         self._clock_config : RealTimeClockConfig
    #         delta = self._clock_config.end_date - self._clock_config.start_date
    #         delay = delta.seconds

    #         await asyncio.sleep(delay)

    #     except asyncio.CancelledError:
    #         return

class AcceleratedRealTimeSimulationManager(AbstractManager):
    """
    ## Accelerated Real Time Simulation Manager Class 
    
    Regulates the start and end of a simulation. Each real-time second represents a fixed number of simulation seconds.

    ### Attributes:
        - _name (`str`): The name of this simulation manager
        - _network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
        - _my_addresses (`list`): List of addresses used by this simulation manager

        - _rep_socket (:obj:`Socket`): The manager's response port socket
        - _rep_socket_lock (:obj:`Lock`): async lock for _rep_socket (:obj:`socket`)
        - _pub_socket (:obj:`Socket`): The manager's broadcast port socket
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket (:obj:`Socket`): The manager's monitor port socket        
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)

        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`AcceleratedRealTimeClockConfig`): description of this simulation's clock configuration
        - _address_ledger (`dict`): ledger containing the addresses pointing to each node's connecting ports

    ### Communications diagram:
    +------------+---------+                
    |            | REP     |<---->>
    | SIMULATION +---------+       
    |   MANAGER  | PUB     |------>
    |            +---------+       
    |            | PUSH    |------>
    +------------+---------+           
    """
    @beartype
    def __init__(self, 
                simulation_element_name_list: list, 
                network_config: ManagerNetworkConfig, 
                clock_config: AcceleratedRealTimeClockConfig,
                level:int = logging.INFO
                ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of the names of all simulation elements
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - clock_config (:obj:`AcceleratedRealTimeClockConfig`): description of this simulation's clock configuration
            - level (`int`): logging level for this simulation element
        """
        super().__init__(simulation_element_name_list, network_config, clock_config, level)

    # async def _live(self):
    #     try:
    #         # wait for simulation duration to pass
    #         self._clock_config : AcceleratedRealTimeClockConfig
    #         delta = self._clock_config.end_date - self._clock_config.start_date
    #         delay = delta.seconds / self._clock_config._sim_clock_freq

    #         await asyncio.sleep(delay)

    #     except asyncio.CancelledError:
    #         return

from datetime import datetime, timezone

if __name__ == "__main__":
    response_address = "tcp://*:5558"
    broadcast_address = "tcp://*:5559"
    monitor_address = "tcp://127.0.0.1:55"
    network_config = ManagerNetworkConfig(response_address, broadcast_address, monitor_address)

    start = datetime(2020, 1, 1, 7, 20, 0, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, 7, 20, 3, tzinfo=timezone.utc)
    clock_config = RealTimeClockConfig(start, end)

    manager = RealTimeSimulationManager([], network_config, clock_config)

    t_o = time.perf_counter()
    manager.run()
    t_f = time.perf_counter()
    
    print(f't_o = {t_o}')
    print(f't_f = {t_f}')
    print(f'dt = {t_f - t_o}')
