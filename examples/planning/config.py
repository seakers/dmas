
import datetime
from enum import Enum

class PlannerTypes(Enum):
    ACBBA = 'ACBBA'

class SimulationConfig(object):
    def __init__(   self, 
                    start_date : datetime,
                    end_date : datetime,
                    bounds : list,
                    agent_range : float,
                    n_tasks : int, 
                    task_score : dict,
                    task_probability : dict, 
                    planner_type : PlannerTypes
                ) -> None:
        self.start_date = start_date
        self.end_date = end_date
        self.bounds = bounds.copy()
        self.agent_range = agent_range
        self.n_tasks : float = n_tasks
        self.task_probability : dict = task_probability
        self.task_score : dict = task_score
        self.planner_type : PlannerTypes = planner_type