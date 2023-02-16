from abc import ABC, abstractmethod
import asyncio
from beartype import beartype
from datetime import datetime, timezone
from enum import Enum
import json

import numpy

"""
------------------
NETWORK CONFIGS
------------------
"""
class ClockTypes(Enum):
    REAL_TIME = 'REAL_TIME'                             # runs simulations in real-time 
    ACCELERATED_REAL_TIME = 'ACCELERATED_REAL_TIME'     # each real time second represents a user-given amount of simulation seconds

class NetworkConfigTypes(Enum):
    MANAGER_NETWORK_CONFIG = 'MANAGER_NETWORK_CONFIG'
    NODE_NETWORK_CONFIG = 'NODE_NETWORK_CONFIG'
    ENVIRONMENT_NETWORK_CONFIG = 'NODE_NETWORK_CONFIG'

class NetworkConfig(ABC):
    """
    ## Abstract Simulation Element Network Configuration

    Describes the addresses assigned to a particular simulation element

    TODO: Add username and password support
    """
    @beartype
    def __init__(self) -> None:
        """
        Initializes an instance of a Network Config Object
        """
        super().__init__()

    @abstractmethod
    def to_dict(self) -> dict:
        """
        Converts object into a dictionary
        """
        pass

    @beartype
    @abstractmethod
    def from_dict(d : dict):
        """
        Creates an instance of this Configuration Class from a dictionary object
        """
        pass

    @abstractmethod
    def from_json(j):
        """
        Creates an instance of this Configuration Class from a json object
        """
        pass

    def __str__(self):
        return str(self.to_dict())

class ParticipantNetworkConfig(NetworkConfig):
    """
    ## Abstract Simulation Participant Network Configuration

    Describes the addresses assigned to a particular simulation element

    ### Attributes:
        - _broadcast_address (`str`): an element's broadcast port address
        - _monitor_address (`str`): the simulation's monitor port address
    """
    @beartype
    def __init__(self, 
                broadcast_address : str, 
                monitor_address : str
                ) -> None:
        """
        Initializes an instance of a Network Config Object

        ### Arguments:
        - broadcast_address (`str`): an element's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        super().__init__()
        self._broadcast_address = broadcast_address
        self._monitor_address = monitor_address

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
    
    def to_dict(self) -> dict:
        out = dict()
        out['broadcast address'] = self.get_broadcast_address()
        out['monitor address'] = self.get_monitor_address()
        return out

class ManagerNetworkConfig(ParticipantNetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager

    ### Attributes:
        - _response_address (`str`): an element's response port address
        - _broadcast_address (`str`): an element's broadcast port address
        - _monitor_address (`str`): the simulation's monitor port address
    """
    def __init__(self, response_address : str, broadcast_address: str, monitor_address: str) -> None:
        """
        Initializes an instance of a Manager Network Config Object
        
        ### Arguments:
        - broadcast_address (`str`): an element's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        super().__init__(broadcast_address, monitor_address)
        self._response_address = response_address
    
    def get_response_address(self) -> str:
        """
        Returns an manager's reponse port address
        """
        return self._response_address

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['response address'] = self.get_response_address()
        out['@type'] = NetworkConfigTypes.MANAGER_NETWORK_CONFIG.name
        return out

    def from_dict(d: dict):
        response_address = d.get('response address', None)
        broadcast_address = d.get('broadcast address', None)
        monitor_address = d.get('monitor address', None)
        config_type = d.get('@type', None)

        if response_address is None or broadcast_address is None or monitor_address is None or config_type is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this network config object.')

        if NetworkConfigTypes[config_type] is not NetworkConfigTypes.MANAGER_NETWORK_CONFIG:
            raise TypeError(f'Cannot load a {NetworkConfigTypes.MANAGER_NETWORK_CONFIG.name} type object from a dictionary describing a {config_type} object.')

        return ManagerNetworkConfig(response_address, broadcast_address, monitor_address)

    def from_json(j):
        return ManagerNetworkConfig.from_dict(json.loads(j))

class NodeNetworkConfig(ParticipantNetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to a simulated node

    ### Attributes:
        - _broadcast_address (`str`): the simulatede node's broadcast port address
        - _monitor_address (`str`): the simulation's monitor port address
        - _manager_address (`str`): the simulation's manager port address
    """
    @beartype
    def __init__(self, 
                broadcast_address: str, 
                monitor_address: str,
                manager_address: str
                ) -> None:
        """
        Initializes an instance of a Node Network Config Object

        ### Arguments:
            - broadcast_address (`str`): an simulated node's broadcast port address
            - monitor_address (`str`): an simulation's monitor port address
            - manager_address (`str`): the simulation's manager port address
        """
        super().__init__(broadcast_address, monitor_address)
        self._manager_address = manager_address

    def get_manager_address(self) -> str:
        """
        Returns a node's simulation manager port address
        """
        return self._manager_address

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['manager address'] = self.get_manager_address()
        out['@type'] = NetworkConfigTypes.NODE_NETWORK_CONFIG.name
        return out

    @beartype
    def from_dict(d: dict):
        broadcast_address = d.get('broadcast address', None)
        monitor_address = d.get('monitor address', None)
        manager_address = d.get('manager address', None)
        config_type = d.get('@type', None)

        if config_type is None or broadcast_address is None or monitor_address is None or manager_address is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this network config object.')

        if NetworkConfigTypes[config_type] is not NetworkConfigTypes.NODE_NETWORK_CONFIG:
            raise TypeError(f'Cannot load a {NetworkConfigTypes.NODE_NETWORK_CONFIG.name} type object from a dictionary describing a {config_type} object.')

        return NodeNetworkConfig(broadcast_address, monitor_address, manager_address)

    def from_json(j):
        return NodeNetworkConfig.from_dict(json.loads(j))

class EnvironmentNetworkConfig(NodeNetworkConfig):
    """
    ## Environment Network Config
    
    Describes the addresses assigned to the simulated environment

    ### Attributes:
        - _response_address (`str`): an environment's response port address
        - _broadcast_address (`str`): an environment's broadcast port address
        - _monitor_address (`str`): the simulation's monitor port address
        - _manager_address (`str`): the simulation's manager port address
    """
    @beartype
    def __init__(self, 
                response_address: str,
                broadcast_address: str, 
                monitor_address: str,
                manager_address: str
                ) -> None:
        """
        Initiates an instance of a Environment Network Config Object

        ### Arguments:
            - response_address (`str`): an environment's response port address
            - broadcast_address (`str`): an environment's broadcast port address
            - monitor_address (`str`): the simulation's monitor port address
            - manager_address (`str`): the simulation's manager port address
        """
        super().__init__(broadcast_address, monitor_address, manager_address)
        self._response_address = response_address

    def get_response_address(self) -> str:
        return self._response_address

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['response address'] = self.get_response_address()
        out['@type'] = NetworkConfigTypes.ENVIRONMENT_NETWORK_CONFIG.name
        return out

    @beartype
    def from_dict(d: dict):
        reponse_address = d.get('response address', None)
        broadcast_address = d.get('broadcast address', None)
        monitor_address = d.get('monitor address', None)
        manager_address = d.get('manager address', None)
        config_type = d.get('@type', None)

        if config_type is None or reponse_address is None or broadcast_address is None or monitor_address is None or manager_address is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this network config object.')

        if NetworkConfigTypes[config_type] is not NetworkConfigTypes.ENVIRONMENT_NETWORK_CONFIG:
            raise TypeError(f'Cannot load a {NetworkConfigTypes.ENVIRONMENT_NETWORK_CONFIG.name} type object from a dictionary describing a {config_type} object.')

        return EnvironmentNetworkConfig(reponse_address, broadcast_address, monitor_address, manager_address)

    def from_json(j):
        return EnvironmentNetworkConfig.from_dict(json.loads(j))

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
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
    """
    def __init__(self, 
                start_date : datetime, 
                end_date : datetime, 
                clock_type : ClockTypes
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
        self.simulation_runtime_start = -1
        self.simulation_runtime_end = -1

    def set_simulation_runtime_start(self, t : float) -> None:
        self.simulation_runtime_start = t

    def set_simulation_runtime_end(self, t : float) -> None:
        self.simulation_runtime_end = t

    def to_dict(self) -> dict:
        """
        Creates an instance of a dictionary containing information about this object
        """
        out = dict()
        out['start date'] = str(self.start_date)
        out['end date'] = str(self.end_date)
        out['@type'] = self.clock_type.name
        return out

    def to_json(self) -> json:
        """
        Creates an instance of a json object containing information about this object
        """
        return json.dumps(self.to_dict())

    @abstractmethod
    def from_dict(d : dict):
        """
        Creates an instance of a clock configuration object from a dictionary 
        """
        pass

    @abstractmethod
    def from_json(j):
        """
        Creates an instance of a clock configuration object from a json object 
        """
        pass

def datetime_from_str(date_str : str) -> datetime:
    """
    Reads a string repersenting a date and a time and returns a datetime object
    """
    date, time = date_str.split(' ')
    year, month, day = date.split('-')
    year, month, day = int(year), int(month), int(day)

    time, delta = time.split('+')
    hh, mm, ss = time.split(':')
    hh, mm, ss = int(hh), int(mm), int(ss)

    dmm, dss = delta.split(':')
    dmm, dss = int(dmm), int(dss)
    
    # print(f'{year}-{month}-{day} {hh}:{mm}:{ss}+{dmm}:{dss}')
    return datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)

class AcceleratedRealTimeClockConfig(ClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - _start_date (:obj:`datetime`): simulation start date
        - _end_date (:obj:`datetime`): simulation end date
        - _clock_type (:obj:`SimClocks`) = `SimClocks.ACCELERATED_REAL_TIME`: type of clock to be used in the simulation
        - _sim_clock_freq (`float`): ratio of simulation-time seconds to real-time seconds [t_sim/t_real]
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
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
        
        super().__init__(start_date, end_date, ClockTypes.ACCELERATED_REAL_TIME)

        if sim_clock_freq < 1:
            raise ValueError('`sim_clock_freq` must be a value greater or equal to 1.')
        
        self.sim_clock_freq = sim_clock_freq

    def to_dict(self) -> dict:
        out = super().to_dict()
        out['clock freq'] = self.sim_clock_freq

    def from_dict(d : dict):
        start_date_str = d.get('start date', None)
        end_date_str = d.get('end date', None)
        clock_frequency = d.get('clock freq', None)
        type_name = d.get('@type', None)

        if start_date_str is None or end_date_str is None or clock_frequency is None or type_name is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this clock config object.')
        
        if type_name != ClockTypes.REAL_TIME.name:
            raise AttributeError(f'Cannot load a Real time Clock Config from a dictionary request of type {type_name}.')
            
        start_date = datetime_from_str(start_date_str)
        end_date = datetime_from_str(end_date_str)

        return AcceleratedRealTimeClockConfig(start_date, end_date, clock_frequency)

    def from_json(j):
        return AcceleratedRealTimeClockConfig.from_dict(json.loads(j))

class RealTimeClockConfig(AcceleratedRealTimeClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (:obj:`datetime`): simulation start date
        - end_date (:obj:`datetime`): simulation end date
        - clock_type (:obj:`SimClocks`) = `SimClocks.REAL_TIME`: type of clock to be used in the simulation
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
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
        super().__init__(start_date, end_date, 1)
        self.clock_type = ClockTypes.REAL_TIME

    def from_dict(d: dict):
        start_date_str = d.get('start date', None)
        end_date_str = d.get('end date', None)
        type_name = d.get('@type', None)

        if start_date_str is None or end_date_str is None or type_name is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this clock config object.')
        
        if type_name != ClockTypes.REAL_TIME.name:
            raise AttributeError(f'Cannot load a Real time Clock Config from a dictionary request of type {type_name}.')
            
        start_date = datetime_from_str(start_date_str)
        end_date = datetime_from_str(end_date_str)

        return RealTimeClockConfig(start_date, end_date)

    def from_json(j):
        return RealTimeClockConfig.from_dict(json.loads(j))

"""
------------------
ASYNCHRONOUS CONTAINER
------------------
"""

class Container:
    def __init__(self, level: float =0, capacity: float =numpy.Infinity):
        if level > capacity:
            raise Exception('Initial level must be lower than maximum capacity.')

        self.level = level
        self.capacity = capacity
        self.updated = None

        self.updated = asyncio.Event()
        self.lock = asyncio.Lock()

    async def set_level(self, value):
        self.level = 0
        await self.put(value)

    async def empty(self):
        self.set_level(0)

    async def put(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level + value <= self.capacity
        
        await self.lock.acquire()
        while not accept():
            self.lock.release()
            self.updated.clear()
            await self.updated.wait()
            await self.lock.acquire()        
        self.level += value
        self.updated.set()
        self.lock.release()

    async def get(self, value):
        if self.updated is None:
            raise Exception('Container not activated in event loop')

        def accept():
            return self.level - value >= 0
        
        await self.lock.acquire()
        while not accept():
            self.lock.release()
            self.updated.clear()
            await self.updated.wait()
            await self.lock.acquire()        
        self.level -= value
        self.updated.set()
        self.lock.release()

    async def when_cond(self, cond):
        if self.updated is None:
            raise Exception('Container not activated in event loop')
             
        while not cond():
            self.updated.clear()
            await self.updated.wait()
        return True

    async def when_not_empty(self):
        def accept():
            return self.level > 0
        
        await self.when_cond(accept)
    
    async def when_empty(self):
        def accept():
            return self.level == 0
        
        await self.when_cond(accept)

    async def when_less_than(self, val):
        def accept():
            return self.level < val
        
        await self.when_cond(accept)
    
    async def when_leq_than(self, val):
        def accept():
            return self.level <= val
        
        await self.when_cond(accept)

    async def when_greater_than(self, val):
        def accept():
            return self.level > val
        
        await self.when_cond(accept)
    
    async def when_geq_than(self, val):
        def accept():
            return self.level >= val
        
        await self.when_cond(accept)