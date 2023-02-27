from abc import ABC, abstractmethod
import datetime
from enum import Enum
import json
from datetime import datetime, timezone

"""
------------------
CLOCK CONFIGS
------------------
"""
class ClockTypes(Enum):
    REAL_TIME = 'REAL_TIME'                             # runs simulations in real-time 
    ACCELERATED_REAL_TIME = 'ACCELERATED_REAL_TIME'     # each real time second represents a user-given amount of simulation seconds

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