from abc import ABC, abstractmethod
import datetime

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
        
        if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise Exception('List of simulation elements must include the simulation environment.')

    async def _activate(self) -> None:
        # initialzie network
        await super()._activate()

        # sync with all simulation elements
        await self._sync_elements()

    async def _sync_elements(self) -> None:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and to become online. Once they do, 
        they will reach out to the manager through its `_peer_in_socket` socket and subscribe to future broadcasts from the 
        manager's `_pub_socket` socket.

        The manager will use this messages to create a ledger mapping simulation elements to their assigned ports. 
        
        This ledger will then be broadcasted to all simulation elements, signaling the start of the simulation.
        """
        element_address_map = dict()
        while len(element_address_map) < len(self._simulation_element_name_list):
            await self._peer_in_socket.recv_json()


    async def _shut_down(self) -> None:
        

        return await super()._shut_down()

    async def _config_network(self):
        return

    def _close_sockets(self) -> None:
        return 