from abc import ABC, abstractmethod
import datetime
from enum import Enum
import json
from datetime import datetime, timedelta, timezone
from typing import Union

"""
------------------
CLOCK CONFIGS
------------------
"""
class ClockTypes(Enum):
    TEST = 'TEST'
    REAL_TIME = 'REAL_TIME'                             # runs simulations in real-time 
    ACCELERATED_REAL_TIME = 'ACCELERATED_REAL_TIME'     # each real time second represents a user-given amount of simulation seconds

class ClockConfig(ABC):
    """
    ## Abstract Simulation Clock Configuration  

    Describes the type of clock being used by the simulation manager.

    ### Attributes:
        - start_date (`str` or `datetime`): simulation start date
        - end_date (`str` or `datetime`): simulation end date
        - clock_type (`str`): type of clock to be used in the simulation
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
    """
    def __init__(self, 
                start_date : Union[str, datetime], 
                end_date : Union[str, datetime], 
                clock_type : str,
                simulation_runtime_start : float = -1.0,
                simulation_runtime_end : float = -1.0,
                **kwargs
                ) -> None:
        """
        Initializes an instance of a clock configuration object

        ### Args:
            - start_date (:obj:`datetime`): simulation start date
            - end_date (:obj:`datetime`): simulation end date
            - clock_type (:obj:`SimClocks`): type of clock to be used in the simulation 
        """
        super().__init__()

        # check types 
        if isinstance(start_date, datetime):
            start_date = str(start_date)
        if isinstance(end_date, datetime):
            end_date = str(end_date)

        if not isinstance(start_date , str):
            raise TypeError(f'Attribute `start_date` must be of type `str`. Is of type {type(start_date)}')
        if not isinstance(end_date , str):
            raise TypeError(f'Attribute `end_date` must be of type `str`. Is of type {type(end_date)}')
        if not isinstance(clock_type , str):
            raise TypeError(f'Attribute `clock_type` must be of type `str`. Is of type {type(clock_type)}')
        if not isinstance(simulation_runtime_start , float) and not isinstance(simulation_runtime_start , int):
            raise TypeError(f'Attribute `simulation_runtime_start` must be of type `float` or `int`. Is of type {type(simulation_runtime_start)}')
        if not isinstance(simulation_runtime_end , float) and not isinstance(simulation_runtime_end , int):
            raise TypeError(f'Attribute `simulation_runtime_end` must be of type `float` or `int`. Is of type {type(simulation_runtime_end)}')
        
        # load attributes from arguments
        self.start_date = str(ClockConfig.str_to_datetime(start_date))
        self.end_date = str(ClockConfig.str_to_datetime(end_date))
        self.clock_type = clock_type
        self.simulation_runtime_start = simulation_runtime_start
        self.simulation_runtime_end = simulation_runtime_end    
 
    def __eq__(self, other) -> bool:
        """
        Compares two instances of a clock configuration. Returns True if they represent the same configuration
        """
        other : ClockConfig
        return self.to_dict() == other.to_dict()

    def set_simulation_runtime_start(self, t : float) -> None:
        self.simulation_runtime_start = t

    def set_simulation_runtime_end(self, t : float) -> None:
        self.simulation_runtime_end = t

    def to_dict(self) -> dict:
        """
        Creates an instance of a dictionary containing information about this object
        """
        return self.__dict__

    def to_json(self) -> json:
        """
        Creates an instance of a json object containing information about this object
        """
        return json.dumps(self.to_dict())

    def get_start_time(self) -> datetime:
        """
        Returns the start date for this clock
        """
        return self.str_to_datetime(self.start_date)

    def get_start_time(self) -> datetime:
        """
        Returns the end date for this clock
        """
        return self.str_to_datetime(self.end_date)

    def str_to_datetime(date_str : str) -> datetime:
        """
        Reads a string repersenting a date and a time and returns a datetime object
        """
        date, time = date_str.split(' ')
        year, month, day = date.split('-')
        year, month, day = int(year), int(month), int(day)

        if '+' in time:
            time, delta = time.split('+')
            hh, mm, ss = time.split(':')
            hh, mm, ss = int(hh), int(mm), int(ss)

            dmm, dss = delta.split(':')
            dmm, dss = int(dmm), int(dss)
        else:
            hh, mm, ss = time.split(':')
            hh, mm, ss = int(hh), int(mm), int(ss)

        return datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)

    @abstractmethod
    def get_total_seconds(self):
        """
        Returns the real-time period to be simulated in seconds
        """
        pass

class AcceleratedRealTimeClockConfig(ClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (`str` or `datetime`): simulation start date
        - end_date (`str` or `datetime`): simulation end date
        - clock_type (`str` or `datetime`): type of clock to be used in the simulation
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
        - sim_clock_freq (`float`): ratio of simulation-time seconds to real-time seconds [t_sim/t_real]
    """

    def __init__(self, 
                start_date : Union[str, datetime], 
                end_date : Union[str, datetime], 
                sim_clock_freq : float,
                **kwargs
                ) -> None:
        """
        Initializes and instance of a Real Time Simulation Clock Configuration  
        
        ### Args:
            - start_date (`str`): simulation start date
            - end_date (`str`): simulation end date
            - sim_clock_freq (`float`): ratio of simulation-time seconds to real-time seconds [t_sim/t_real]
        """        
        
        super().__init__(start_date, end_date, ClockTypes.ACCELERATED_REAL_TIME.value)

        if not isinstance(sim_clock_freq, int) and not isinstance(sim_clock_freq, float):
            raise TypeError(f'Attribute `sim_clock_freq` must be of type `float` or `int`. Is of type {type(sim_clock_freq)}')
        if sim_clock_freq < 1:
            raise ValueError('`sim_clock_freq` must be a value greater or equal to 1.')
        
        self.sim_clock_freq = sim_clock_freq

    def get_total_seconds(self):
        delta : timedelta = ClockConfig.str_to_datetime(self.end_date) - ClockConfig.str_to_datetime(self.start_date)
        return delta.total_seconds()/self.sim_clock_freq

class RealTimeClockConfig(AcceleratedRealTimeClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (`str` or `datetime`): simulation start date
        - end_date (`str` or `datetime`): simulation end date
        - clock_type (`str`): type of clock to be used in the simulation
        - simulation_runtime_start (`float`): real-clock start time of the simulation
        - simulation_runtime_end (`float`): real-clock end time of the simulation
    """
    def __init__(self, 
                start_date : Union[str, datetime], 
                end_date : Union[str, datetime], 
                **kwargs
                ) -> None:
        """
        Initializes and instance of a Real Time Simulation Clock Configuration  
        
        ### Attributes:
            - start_date (:obj:`datetime`): simulation start date
            - end_date (:obj:`datetime`): simulation end date
        """
        super().__init__(start_date, end_date, 1.0)