from abc import ABC, abstractmethod
import asyncio
from beartype import beartype
from datetime import datetime, timezone
from enum import Enum
import json

import numpy
import zmq

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
    def __init__(self, internal_address_map : dict, external_address_map : dict) -> None:
        super().__init__()  
        # check map format
        for map in [internal_address_map, external_address_map]:
            for socket_type in map:
                addresses = map[socket_type]

                if not isinstance(addresses, list):
                    if map == internal_address_map:
                        raise TypeError(f'Internal Address Map must be comprised of elements of type {type(list)}. Is of type {type(addresses)}')
                    else:
                        raise TypeError(f'External Address Map must be comprised of elements of type {type(list)}. Is of type {type(addresses)}')

                for address in addresses:   
                    if not isinstance(socket_type, zmq.SocketType):
                        if map == internal_address_map:
                            raise TypeError(f'{socket_type} in Internal Address Map must be of type {type(zmq.SocketType)}. Is of type {type(socket_type)}')
                        else:
                            raise TypeError(f'{socket_type} in External Address Map must be of type {type(zmq.SocketType)}. Is of type {type(socket_type)}')
                    elif not isinstance(address, str):
                        if map == internal_address_map:
                            raise TypeError(f'{address} in Internal Address Map must be of type {type(str)}. Is of type {type(address)}')
                        else:
                            raise TypeError(f'{address} in External Address Map must be of type {type(str)}. Is of type {type(address)}')

        # save addresses
        self._internal_address_map = internal_address_map.copy()
        self._external_address_map = external_address_map.copy()

    def get_internal_addresse(self) -> dict:
        return self._internal_address_map

    def get_external_addresses(self) -> dict:
        return self._external_address_map

    def to_dict(self) -> dict:
        out = dict()
        # out['internal addresses'] = str(self._internal_address_map) # internal addresses are NOT to be shared
        out['external addresses'] = str(self._internal_address_map)
        return out

    def from_dict(d : dict):
        # internal_addresses = d.get('internal addresses', None)
        external_addresses = d.get('external addresses', None)

        if external_addresses is None:
            raise AttributeError('Dictionary does not contain necessary information to construct this network config object.')
        
        return NetworkConfig(external_addresses=external_addresses)
    
    def to_json(self) -> str:
        return json.dump(self.to_dict())

    def from_json(j : str):
        return NetworkConfig.from_dict(json.loads(j))

class ManagerNetworkConfig(NetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager
    """
    def __init__(self, 
                response_address : str,
                broadcast_address: str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of a Manager Network Config Object
        
        ### Arguments:
        - response_address (`str`): a manager's response port address
        - broadcast_address (`str`): a manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        external_address_map = {zmq.REP: [response_address], zmq.PUB: [broadcast_address], zmq.PUSH: monitor_address}
        super().__init__(external_address_map=external_address_map)

class AgentNetworkConfig(NetworkConfig):
    """
    ## Agent Network Config
    
    Describes the addresses assigned to a simulation agent node
    """
    def __init__(self, 
                internal_send_address: str,
                internal_recv_addresses : list,
                broadcast_address: str, 
                manager_address : str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of an Agent Network Config Object
        
        ### Arguments:
        - internal_send_address (`str`): an agent's internal bradcast port address
        - internal_recv_addresses (`list`): list of an agent's modules' publish port addresses
        - broadcast_address (`str`): an agent's broadcast port address
        - manager_address (`str`): the simulation manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        internal_address_map = {zmq.PUB:  [internal_send_address],
                                zmq.SUB:  internal_recv_addresses}
        external_address_map = {zmq.REQ:  [],
                                zmq.PUB:  [broadcast_address],
                                zmq.SUB:  [manager_address],
                                zmq.PUSH: [monitor_address]}

        super().__init__(internal_address_map, external_address_map)

class InternalModuleNetworkConfig(NetworkConfig):
    """
    ## Internal Module Network Config
    
    Describes the addresses assigned to a node's internal module 
    """
    def __init__(self, 
                module_send_address: str, 
                module_recv_address: str
                ) -> None:
        """
        Initializes an instance of an Internal Module Network Config Object
        
        ### Arguments:
        - module_recv_address (`str`): an internal module's parent agent node's broadcast address
        - module_send_address (`str`): the internal module's broadcast address
        """
        external_address_map = {zmq.SUB: [module_recv_address],
                                zmq.PUB: [module_send_address]}       
        super().__init__(external_address_map=external_address_map)

class EnvironmentNetworkConfig(NetworkConfig):
    """
    ## Environment Network Config
    
    Describes the addresses assigned to a simulation environment node
    """
    def __init__(self, 
                internal_send_addresses: list,
                internal_recv_address : str,
                response_address : str,
                broadcast_address: str, 
                manager_address : str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of an Agent Network Config Object
        
        ### Arguments:
        - internal_send_addresses (`list`): list of the environment's workers' port addresses
        - internal_recv_address (`str`): the environment's internal listening port address
        - response_address (`str`): the environment's response port address
        - broadcast_address (`str`): the environment's broadcast port address
        - manager_address (`str`): the simulation manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        internal_address_map = {zmq.PUB:  internal_send_addresses,
                                zmq.SUB:  [internal_recv_address]}
        external_address_map = {zmq.REQ:  [],
                                zmq.REP:  [response_address],
                                zmq.PUB:  [broadcast_address],
                                zmq.SUB:  [manager_address],
                                zmq.PUSH: [monitor_address]}

        super().__init__(internal_address_map, external_address_map)

class EnvironmentWorkerModuleNetworkConfig(NetworkConfig):
    """
    ## Environment Worker Module Network Config
    
    Describes the addresses assigned to an environment's internal worker module 
    """
    def __init__(self, 
                module_send_address: str, 
                module_recv_address: str
                ) -> None:
        """
        Initializes an instance of an Environemtn Worker Module Network Config Object
        
        ### Arguments:
        - module_send_address (`str`): an internal module's parent agent node's broadcast address
        - module_recv_address (`str`): the internal module's broadcast address
        """
        external_address_map = {zmq.PUSH: [module_send_address],
                                zmq.PULL: [module_recv_address]}       
        super().__init__(external_address_map=external_address_map)

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