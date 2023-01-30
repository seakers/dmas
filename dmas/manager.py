from abc import ABC, abstractmethod
import datetime

from .utils import *

from .element import SimulationElement

class AbstractManager(SimulationElement, ABC):
    """
    ## Abstract Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time
    """

    def __init__(self, 
            simulation_element_name_list : list,
            clock_config : ClockConfig,
            response_address: str, 
            broadcast_address: str, 
            monitor_address: str,
            ) -> None:
        """
        Initializes and instance of a simulation manager
        """
        super().__init__(SimulationElementTypes.MANAGER.name, 
                        response_address, 
                        broadcast_address,
                        monitor_address)

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config
        
        if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise Exception('List of simulation elements must include the simulation environment.')

    async def _network_config(self) -> None:
        pass