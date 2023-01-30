from abc import ABC
import datetime
from enum import Enum

class SimClocks(Enum):
    # asynchronized clocks
    # -Each node in the network carries their own clocks to base their waits on
    REAL_TIME = 'REAL_TIME'                             # runs simulations in real-time. 
    ACCELERATED_REAL_TIME = 'ACCELERATED_REAL_TIME'     # each real time second represents a user-given amount of simulation seconds

class SimulationElementTypes(Enum):
    MANAGER = 'MANAGER'
    ENVIRONMENT = 'ENVIRONMENT'

class ClockConfig(ABC):
    """
    ## Abstract Simulation Clock Configuration  

    Describes the type of clock being used by the simulation manager.

    ### Attributes:
        start_date (:obj:`datetime`): simulation start date
        end_date (:obj:`datetime`): simulation end date
        clock_type (:obj:`SimClocks`): type of clock to be used in the simulation
    """
    def __init__(self, 
                start_date : datetime, 
                end_date : datetime, 
                clock_type : SimClocks) -> None:
        """
        Initializes an instance of a clock configuration object

        ### Args:
            start_date (:obj:`datetime`): simulation start date
            end_date (:obj:`datetime`): simulation end date
            clock_type (:obj:`SimClocks`): type of clock to be used in the simulation 
        """
        self.start_date = start_date
        self.end_date = end_date
        self.clock_type = clock_type

class RealTimeClock(ClockConfig):
    """
    ## Real Time Simulation Clock Configuration  

    Describes a real-time clock to be used in the simulation.

    ### Attributes:
        - start_date (:obj:`datetime`): simulation start date
        - end_date (:obj:`datetime`): simulation end date
        - clock_type (:obj:`SimClocks`) = `SimClocks.REAL_TIME`: type of clock to be used in the simulation
    """
    def __init__(self, start_date: datetime, end_date: datetime) -> None:
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

    def __init__(self, start_date: datetime, end_date: datetime, sim_clock_freq : float) -> None:
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