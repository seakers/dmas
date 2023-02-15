import logging
from dmas.element import *
from dmas.participant import Participant
from dmas.utils import *


class AbstractManager(Participant):
    """
    ## Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Additional Attributes:
        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
        

    ### Communications diagram:
    +------------+---------+                
    |            | REP     |<---->>
    | SIMULATION +---------+       
    |   MANAGER  | PUB     |------>
    |            +---------+       
    |            | PUSH    |------>
    +------------+---------+             
    """
    __doc__ += SimulationElement.__doc__
    
    @beartype
    def __init__(self, 
            simulation_element_name_list : list,
            clock_config : ClockConfig,
            network_config : ManagerNetworkConfig,
            level : int = logging.INFO
            ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of the names of all simulation elements
            - clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - level (`int`): logging level for this simulation element
        """
        super().__init__(SimulationElementRoles.MANAGER.name, network_config, level)

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._offline_simulation_element_list = []
        self._clock_config = clock_config
        
        # if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
        #     raise RuntimeError('List of simulation elements must include the simulation environment.')

        # TODO check if there is more than one environment in the list 

    def _config_network(self) -> list:
        port_list : dict = super()._config_network()

        # direct message response port
        self._network_config : ManagerNetworkConfig
        rep_socket : zmq.Socket = self._context.socket(zmq.REP)
        peer_in_address : str = self._network_config.get_response_address()
        rep_socket.bind(peer_in_address)
        rep_socket.setsockopt(zmq.LINGER, 0)
        rep_socket_lock = threading.Lock()

        port_list[zmq.REP] = (rep_socket, rep_socket_lock)

        return port_list

    def _sync() -> dict:
        # wait for all simulation elements to initialize and connect to me

        # broadcast start of simulation to all 
        pass