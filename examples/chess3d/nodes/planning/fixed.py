import asyncio
import logging
from nodes.states import GroundStationAgentState, SatelliteAgentState, SimulationAgentTypes, UAVAgentState
from nodes.agent import *
from messages import *
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig
from nodes.planning.planners import PlanningModule


class FixedPlanner(PlanningModule):
    def __init__(self, 
                results_path: str, 
                parent_name: str, 
                plan : list,
                parent_network_config: NetworkConfig, 
                utility_func: Callable[[], Any],
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   results_path, 
                            parent_name, 
                            parent_network_config, 
                            utility_func, 
                            level, 
                            logger
                        )
        self.plan = plan        

    async def planner(self) -> None:
        try:
            t_curr = 0
            while True:
                plan_out = []
                state_msg : AgentStateMessage = await self.states_inbox.get()

                # update current time:
                state : SimulationAgentState = SimulationAgentState.from_dict(state_msg.state)

                if t_curr < state.t:
                    t_curr = state.t

                while not self.action_status_inbox.empty():
                    action_msg : AgentActionMessage = await self.action_status_inbox.get()

                    if action_msg.status != AgentAction.COMPLETED and action_msg.status != AgentAction.ABORTED:
                        # if action wasn't completed, re-try
                        action_dict : dict = action_msg.action
                        self.log(f'action {action_dict} not completed yet! trying again...')
                        plan_out.append(action_dict)

                    elif action_msg.status == AgentAction.COMPLETED:
                        # if action was completed, remove from plan
                        action_dict : dict = action_msg.action
                        completed_action = AgentAction(**action_dict)
                        removed = None
                        for action in self.plan:
                            action : AgentAction
                            if action.id == completed_action.id:
                                removed = action
                                break

                        if removed is not None:
                            self.plan.remove(removed)

                while not self.measurement_req_inbox.empty():
                    # ignore measurement requests
                    req_msg : MeasurementRequestMessage = await self.measurement_req_inbox.get()
                
                plan_out_id = [action['id'] for action in plan_out]
                for action in self.plan:
                    action : AgentAction
                    if (action.t_start <= t_curr <= action.t_end
                        and action.id not in plan_out_id):
                        plan_out.append(action.to_dict())

                if len(plan_out) == 0:
                    # if no plan left, just idle for a time-step
                    self.log('no more actions to perform. instruct agent to idle for the remainder of the simulation.')
                    if len(self.plan) > 0:
                        next_action : AgentAction = self.plan[0]
                        t_idle = next_action.t_start
                    else:
                        t_idle = t_curr + 1e8 # TODO find end of simulation time        
                    action = WaitForMessages(t_curr, t_idle)
                    plan_out.append(action.to_dict())
                    
                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

        except Exception as e:
            self.log(f'routine failed. {e}')
            raise e

    async def teardown(self) -> None:
        # nothing to tear-down
        return

    def can_do(self, **_) -> bool:
        return False

    def predict_access_intervals(self, **_) -> list:
        return []