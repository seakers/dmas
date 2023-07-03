import asyncio
import logging
from typing import Any, Callable
from instrupy.base import Instrument

import zmq
from dmas.network import NetworkConfig
from nodes.science.reqs import MeasurementRequest
from nodes.states import *
from applications.planning.actions import WaitForMessages
from dmas.agents import AgentAction
from messages import *
from nodes.planning.planners import PlanningModule


class GreedyPlanner(PlanningModule):
    """
    Schedules masurement request tasks on a first-come, first-served basis.
    """
    def __init__(self, 
                results_path: str, 
                parent_name: str, 
                parent_network_config: NetworkConfig, 
                utility_func: Callable[[], Any], 
                payload : list,
                level: int = logging.INFO, 
                logger: logging.Logger = None) -> None:
        super().__init__(results_path, parent_name, parent_network_config, utility_func, level, logger)
        self.payload = payload

    async def planner(self) -> None:
        try:
            t_curr = 0
            bundle = []
            reqs_received = []

            while True:
                plan_out = []
                state_msg : AgentStateMessage = await self.states_inbox.get()

                # update current time:
                if state_msg.state['state_type'] == SimulationAgentTypes.SATELLITE.value:
                    state = SatelliteAgentState(**state_msg.state)
                elif state_msg.state['state_type'] == SimulationAgentTypes.UAV.value:
                    state = UAVAgentState(**state_msg.state)
                else:
                    raise NotImplementedError(f"`state_type` {state_msg.state['state_type']} not supported.")

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
                            self.plan : list
                            self.plan.remove(removed)

                while not self.measurement_req_inbox.empty():
                    # replan measurement plan

                    # unpack measurement request
                    req_msg : MeasurementRequestMessage = await self.measurement_req_inbox.get()
                    req = MeasurementRequest.from_dict(req_msg.req)

                    # add to list of known requirements
                    if req.id not in reqs_received:
                        reqs_received.append(req.id)

                        # check if can be added to plan
                        if self.can_do(state, bundle, req):
                            bundle.append(req)

                        self.plan = self.plan_from_bundle(bundle)

                for action in self.plan:
                    action : AgentAction
                    if action.t_start <= t_curr <= action.t_end:
                        plan_out.append(action.to_dict())
                        break

                if len(plan_out) == 0:
                    # if no plan left, just idle for a time-step
                    self.log('no more actions to perform. instruct agent to idle for the remainder of the simulation.')
                    t_idle = t_curr + 1e6 # TODO find end of simulation time        
                    action = WaitForMessages(t_curr, t_idle)
                    plan_out.append(action.to_dict())
                    
                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

    def can_do(self, state: SimulationAgentState, bundle : list, req: MeasurementRequest) -> bool:
        """
        Check if the parent agent is capable of performing a measurement request

        ### Arguments:
            - state (:obj:`SimulatrionAgentState`) : latest known state of parent agent
            - req (:obj:`MeasurementRequest`) : measurement request being considered

        ### Returns:
            - can_do (`bool`) : `True` if agent has the capability to perform a task of `False` if otherwise
        """
        # check if agent has at least one of the required instruments to perform the task
        payload_names = [instrument.name for instrument in self.payload]
        payload_check = False
        for measurement in req.measurements:
            if measurement in payload_names:
                payload_check = True
                break
        
        if not payload_check:
            return False

        # check if task can be fit in current bundle 
        bundle_check = False
        

        return bundle_check

    def predict_access_intervals(self, state: SimulationAgentState, req: MeasurementRequest) -> list:
        """
        Predicts a list of time intervals in [s] when an agent may be able to perform a given measurement request

        ### Arguments
            - state (:obj:`SimulatrionAgentState`) : latest known state of parent agent
            - req (:obj:`MeasurementRequest`) : measurement request being considered

        #### Returns:
            - access_time (`float`) : time at which an agent may 
        """
        # TODO
        pass

    def plan_from_bundle(self, bundle : list) -> list:
        """
        Converts a list of measurement requests into a plan to be performed by the parent agent

        ### Arguments:
            - bundle (`list`) : list of accepted measurement requests to be performed

        ### Returns:
            - plan (`list`) : list of agent actions to be performed by parent agent
        """
        # TODO
        pass

    async def teardown(self) -> None:
        # Nothing to teardown
        return