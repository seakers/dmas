from abc import ABC, abstractmethod
import datetime
import logging

from .messages import *

from .utils import *

from .element import AbstractSimulationElement

class AbstractManager(AbstractSimulationElement):
    """
    ## Abstract Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Attributes:
        
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
        self._address_map = dict()
        
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
        
        while len(self._address_map) < len(self._simulation_element_name_list):
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
                if src not in self._address_map:
                    # node is a part of the simulation and has not yet been synchronized

                    # add node network information to address map
                    self._address_map[src] = sync_req.get_network_config()
                    logging.debug(f'Node {sync_req.get_src()} is now synchronized! Sync status: ({len(self._address_map)}/{len(self._simulation_element_name_list)})')
                else:
                    # node is a part of the simulation but has already been synchronized
                    logging.debug(f'Node {sync_req.get_src()} is already synchronized to the simulation manager. Sync status: ({len(self._address_map)}/{len(self._simulation_element_name_list)})')
            else:
                    # node is not a part of the simulation
                    logging.debug(f'Node {sync_req.get_src()} not part of this simulation. Sync status: ({len(self._address_map)}/{len(self._simulation_element_name_list)})')
            
            # send synchronization acknowledgement
            await self._peer_in_socket.send_string('ACK')                
        

    async def _shut_down(self) -> None:
        

        return await super()._shut_down()

    async def _config_network(self):
        return

    def _close_sockets(self) -> None:
        return 