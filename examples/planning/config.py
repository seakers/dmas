
import datetime
from enum import Enum

class PlannerTypes(Enum):
    ACBBA = 'ACBBA'

class SimulationConfig(object):
    def __init__(   self, 
                    start_date : datetime,
                    end_date : datetime,
                    bounds : list,
                    agent_comms_range : float,
                    n_agents : int,
                    planner_type : PlannerTypes,
                    n_tasks : int, 
                    task_types : list
                ) -> None:
        # time config
        self.start_date = start_date
        self.end_date = end_date

        # task config
        self.n_tasks = n_tasks
        self.task_types = task_types

        # environment config
        self.bounds = bounds.copy()
        self.agent_comms_range = agent_comms_range

        # agent config
        self.n_agents = n_agents
        self.planner_type = planner_type

        
        