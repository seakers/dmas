import asyncio
import logging
from nodes.planning.fixed import FixedPlanner
from nodes.states import GroundStationAgentState, SatelliteAgentState, UAVAgentState
from nodes.agent import *
from messages import *
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig
from nodes.planning.planners import PlanningModule


class GroundStationPlanner(FixedPlanner):
    def __init__(self, 
                results_path: str, 
                parent_name: str, 
                measurement_reqs : list,
                parent_network_config: NetworkConfig, 
                utility_func: Callable[[], Any], 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        
        # create an initial plan
        plan = []
        for measurement_req in measurement_reqs:
            # broadcast every initialy known measurement requests
            measurement_req : MeasurementRequest
            msg = MeasurementRequestMessage(parent_name, parent_name, measurement_req.to_dict())
            action = BroadcastMessageAction(msg.to_dict(), measurement_req.t_start)
            plan.append(action)

        super().__init__(   results_path, 
                            parent_name, 
                            plan, 
                            parent_network_config, 
                            utility_func, 
                            level, 
                            logger
                        )