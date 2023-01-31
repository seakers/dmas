from abc import ABC, abstractmethod
import asyncio
import datetime
import logging
import time

from .messages import *

from .utils import *

from .element import AbstractSimulationElement

class AbstractManager(AbstractSimulationElement):
    """
    ## Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Attributes:
        - _name (`str`): The name of this simulation element
        - _response_address (`str`): This element's response port address
        - _broadcast_address (`str`): This element's broadcast port address
        - _monitor_address (`str`): This simulation's monitor port address

        - _my_addresses (`list`): List of addresses used by this simulation manager

        - _peer_in_socket (:obj:`Socket`): The element's response port socket
        - _pub_socket (:obj:`Socket`): The element's broadcast port socket
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket

        - _peer_in_socket_lock (:obj:`Lock`): async lock for _peer_in_socket (:obj:`socket`)
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`socket`)
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`socket`)

        - _simulation_element_list (`list`):
        - _clock_config (:obj:`ClockConfig)

    ### Communications diagram:
    +----------+---------+       
    |          | PUB     |------>
    |          +---------+       
    |          | PUSH    |------>
    |          +---------+       
    |          | REP     |<------
    |          +---------+       
    |                    |       
    | SIMULATION MANAGER |       
    +--------------------+           
    """

    def __init__(self, 
            simulation_element_name_list : list,
            network_config : ManagerNetworkConfig,
            clock_config : ClockConfig,
            ) -> None:
        """
        Initializes and instance of a simulation manager
        """
        super().__init__(SimulationElementTypes.MANAGER.name, network_config)

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config
        self._address_ledger = dict()
        
        if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise Exception('List of simulation elements must include the simulation environment.')

    async def _activate(self) -> None:
        # initialzie network
        await super()._activate()

        # sync with all simulation elements
        await self._sync_elements()

        # announce sim start
        await self._broadcast_sim_start()

    async def _sync_elements(self) -> None:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and to become online. 
        
        Once done, elements will reach out to the manager through its `_peer_in_socket` socket and subscribe to future broadcasts 
        from the manager's `_pub_socket` socket.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports. 
        """
        
        while len(self._address_ledger) < len(self._simulation_element_name_list):
            # wait for incoming messages
            msg_dict = await self._peer_in_socket.recv_json()
            msg_type = msg_dict['@type']
            
            if NodeMessageTypes[msg_type] != NodeMessageTypes.SYNC_REQUEST:
                # ignore all incoming messages that are not Sync Requests
                await self._peer_in_socket.send_string('')
                continue

            # unpack and sync message
            sync_req = SyncRequestMessage.from_dict(msg_dict)

            logging.debug(f'Received sync request from node {sync_req.get_src()}!')

            # log subscriber confirmatoin
            src = sync_req.get_src()
            if src in self._simulation_element_name_list:
                if src not in self._address_ledger:
                    # node is a part of the simulation and has not yet been synchronized

                    # add node to network information to address map
                    self._address_ledger[src] = sync_req.get_network_config()
                    logging.debug(f'Node {sync_req.get_src()} is now synchronized! Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
                else:
                    # node is a part of the simulation but has already been synchronized
                    logging.debug(f'Node {sync_req.get_src()} is already synchronized to the simulation manager. Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            else:
                    # node is not a part of the simulation
                    logging.debug(f'Node {sync_req.get_src()} is not part of this simulation. Sync status: ({len(self._address_ledger)}/{len(self._simulation_element_name_list)})')
            
            # send synchronization acknowledgement
            await self._peer_in_socket.send_string('ACK')     

        # broadcast simulation information message
        sim_info_msg = SimulationInfoMessage(self._address_ledger, self._clock_config, time.perf_counter())
        await self._broadcast_message(sim_info_msg)

    async def _broadcast_sim_start(self) -> None:
        """
        Broadcasts this manager's simulation element address ledger to all subscribed elements to signal the start of the simulation.
        """
        # wait for every simulation node to be ready
        elements_ready = []
        while len(elements_ready) < len(self._simulation_element_name_list):
            # wait for incoming messages
            msg_dict = await self._peer_in_socket.recv_json()
            msg_type = msg_dict['@type']
            
            if NodeMessageTypes[msg_type] != NodeMessageTypes.NODE_READY:
                # ignore all incoming messages that are not Sync Requests
                await self._peer_in_socket.send_string('')
                continue

            # unpack and sync message
            ready_msg = NodeReadyMessage.from_dict(msg_dict)

            logging.debug(f'Received ready message from node {ready_msg.get_src()}!')

            # log subscriber confirmatoin
            src = ready_msg.get_src()
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
            
            # send synchronization acknowledgement
            await self._peer_in_socket.send_string('ACK')    
        
        # broadcast sim start  message
        sim_start_msg = SimulationStartMessage(time.perf_counter())
        await self._broadcast_message(sim_start_msg)

    async def _shut_down(self) -> None:
        # broadcast sim end message
        sim_start_msg = SimulationStartMessage(time.perf_counter())
        await self._broadcast_message(sim_start_msg)

        # TODO wait for confirmation from all simulation elements
        
        return await super()._shut_down()

class RealTimeSimulationManager(AbstractManager):
    async def _live(self):
        # wait simtime       
        

        await asyncio.sleep(delay)