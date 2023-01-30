from abc import ABC, abstractmethod
import datetime
from enum import Enum
import json

class SimulationElementTypes(Enum):
    MANAGER = 'MANAGER'
    ENVIRONMENT = 'ENVIRONMENT'
    ALL = 'ALL'

"""
------------------
NETWORK CONFIGS
------------------
"""
class SimClocks(Enum):
    # asynchronized clocks
    # -Each node in the network carries their own clocks to base their waits on
    REAL_TIME = 'REAL_TIME'                             # runs simulations in real-time. 
    ACCELERATED_REAL_TIME = 'ACCELERATED_REAL_TIME'     # each real time second represents a user-given amount of simulation seconds

class NetworkConfig(ABC):
    """
    ## Abstract Simulation Element Network Configuration

    Describes the addresses assigned to a particular simulation element

    ### Attributes:
        - _response_address (`str`): an element's response port address
        - _broadcast_address (`str`): an element's broadcast port address
        - _monitor_address (`str`): an simulation's monitor port address

    TODO: Add username and password support
    """

    def __init__(self, 
                response_address : str, 
                broadcast_address : str, 
                monitor_address : str
                ) -> None:
        """
        Initializes an instance of a Network Config Object
        """
        super().__init__()
        
        self._response_address = response_address
        self._broadcast_address = broadcast_address
        self._monitor_address = monitor_address

    def get_response_address(self) -> str:
        """
        Returns an element's reponse port address
        """
        return self._response_address

    def get_broadcast_address(self) -> str:
        """
        Returns an element's broadcast port address
        """
        return self._broadcast_address

    def get_monitor_address(self) -> str:
        """
        Returns an element's monitor port address 
        """
        return self._monitor_address

    @abstractmethod
    def get_my_addresses(self) -> dict:
        """
        Returns a dictionary of all addresses assigned to a simulation element
        """
        pass

    def to_dict(self) -> dict:
        """
        Converts object into a dictionary
        """
        out = dict()
        out['response address'] = self.get_response_address()
        out['broadcast address'] = self.get_broadcast_address()
        out['monitor address'] = self.get_monitor_address()
        return out

class ManagerNetworkConfig(NetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager

    ### Attributes:
        - _response_address (`str`): an element's response port address
        - _broadcast_address (`str`): an element's broadcast port address
        - _monitor_address (`str`): an simulation's monitor port address
    """
    def get_my_addresses(self) -> dict:
        return [self._response_address, self._broadcast_address]

class NodeNetworkConfig(NetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager

    ### Attributes:
        - _request_address (`str`): an element's request port address
        - _response_address (`str`): an element's response port address
        - _broadcast_address (`str`): an element's broadcast port address
        - _subscribe_address (`str`): an element's subscribe port address
        - _monitor_address (`str`): an simulation's monitor port address
    """
    def __init__(self, 
                request_address: str,
                response_address: str, 
                broadcast_address: str, 
                subscribe_address: str,
                monitor_address: str
                ) -> None:
        super().__init__(response_address, broadcast_address, monitor_address)

        self._request_address = request_address
        self._subscribe_address = subscribe_address

    def get_my_addresses(self) -> dict:
        return [self._request_address, self._response_address, self._broadcast_address, self._subscribe_address]

    def get_request_address(self) -> str:
        """
        Returns a node's request port address 
        """
        return self._request_address

    def get_subscribe_address(self) -> str:
        """
        Returns a node's subscribe port address 
        """
        return self._subscribe_address

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['request address'] = self.get_request_address()
        out['subscribe address'] = self.get_subscribe_address()
        return out

"""
------------------
CLOCK CONFIGS
------------------
"""
class ClockConfig(ABC):
    """
    ## Abstract Simulation Clock Configuration  

    Describes the type of clock being used by the simulation manager.

    ### Attributes:
        - start_date (:obj:`datetime`): simulation start date
        - end_date (:obj:`datetime`): simulation end date
        - clock_type (:obj:`SimClocks`): type of clock to be used in the simulation
    """
    def __init__(self, 
                start_date : datetime, 
                end_date : datetime, 
                clock_type : SimClocks
                ) -> None:
        """
        Initializes an instance of a clock configuration object

        ### Args:
            - start_date (:obj:`datetime`): simulation start date
            - end_date (:obj:`datetime`): simulation end date
            - clock_type (:obj:`SimClocks`): type of clock to be used in the simulation 
        """
        super().__init__()

        self.start_date = start_date
        self.end_date = end_date
        self.clock_type = clock_type

    def to_dict(self) -> dict:
        """
        Creates an instance of a dictionary containing information about this object
        """
        out = dict()
        out['start date'] = self.start_date
        out['end date'] = self.end_date
        out['@type'] = self.clock_type.name
        return out

    def to_json(self) -> json:
        """
        Creates an instance of a json object containing information about this object
        """
        return json.dumps(self.to_dict())

    @abstractmethod
    def from_dict():
        """
        Creates an instance of a clock configuration object from a dictionary 
        """
        pass

    @abstractmethod
    def from_json():
        """
        Creates an instance of a clock configuration object from a json object 
        """
        pass

class RealTimeClock(ClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (:obj:`datetime`): simulation start date
        - end_date (:obj:`datetime`): simulation end date
        - clock_type (:obj:`SimClocks`) = `SimClocks.REAL_TIME`: type of clock to be used in the simulation
    """
    def __init__(self, 
                start_date: datetime, 
                end_date: datetime
                ) -> None:
        """
        Initializes and instance of a Real Time Simulation Clock Configuration  
        
        ### Attributes:
            - start_date (:obj:`datetime`): simulation start date
            - end_date (:obj:`datetime`): simulation end date
        """
        super().__init__(start_date, end_date, SimClocks.REAL_TIME)

class AcceleratedRealTimeClock(ClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (:obj:`datetime`): simulation start date
        - end_date (:obj:`datetime`): simulation end date
        - clock_type (:obj:`SimClocks`) = `SimClocks.ACCELERATED_REAL_TIME`: type of clock to be used in the simulation
        - sim_clock_freq (`float`): ratio of simulation-time seconds to real-time seconds [t_sim/t_real]
    """

    def __init__(self, 
                start_date: datetime, 
                end_date: datetime, 
                sim_clock_freq : float
                ) -> None:
        """
        Initializes and instance of a Real Time Simulation Clock Configuration  
        
        ### Args:
            - start_date (:obj:`datetime`): simulation start date
            - end_date (:obj:`datetime`): simulation end date
            - sim_clock_freq (`float`): ratio of simulation-time seconds to real-time seconds [t_sim/t_real]
        """        
        
        super().__init__(start_date, end_date, SimClocks.ACCELERATED_REAL_TIME)

        if sim_clock_freq < 1:
            raise ValueError('`sim_clock_freq` must be a value greater or equal to 1.')

class LoggerTypes(Enum):
    DEBUG = 'DEBUG'
    ACTIONS = 'ACTIONS'
    AGENT_TO_ENV_MESSAGE = 'AGENT_TO_ENV_MESSAGE'
    ENV_TO_AGENT_MESSAGE = 'ENV_TO_AGENT_MESSAGE'
    AGENT_TO_AGENT_MESSAGE = 'AGENT_TO_AGENT_MESSAGE'
    INTERNAL_MESSAGE = 'INTERNAL_MESSAGE'
    STATE = 'STATE'
    RESULTS = 'RESULTS'