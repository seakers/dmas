import copy
import logging
import math
import os
import re
import time
import pandas as pd
import numpy as np
import zmq
from typing import Any, Callable, Union
from nodes.science.reqs import MeasurementRequest, GroundPointMeasurementRequest
from nodes.planning.planners import Bid, PlanningModule
from nodes.orbitdata import OrbitData
from nodes.states import SatelliteAgentState, SimulationAgentTypes, SimulationAgentState, UAVAgentState
from nodes.actions import *
from messages import *
from dmas.agents import AgentAction
from dmas.network import NetworkConfig

class MCCBBA(PlanningModule):
    def __init__(   self, 
                    results_path: str, 
                    parent_name: str, 
                    parent_network_config: NetworkConfig, 
                    utility_func: Callable[[], Any], 
                    payload : list,
                    max_bundle_size = 4,
                    planning_horizon = 3600,
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
        self.stats = {
                        "consensus" : [],
                        "planning" : [],
                        "doing" : [],
                        "c_comp_check" : [],
                        "c_t_end_check" : [],
                        "c_const_check" : []
                    }
        self.plan_history = []
        self.iter_counter = 0
        self.payload = payload
        self.max_bundle_size = max_bundle_size
        self.planning_horizon = planning_horizon
        self.parent_agent_type = None
    
    async def planner(self) -> None:
        try:
            results, bundle, path, plan, prev_actions = {}, [], [], [], []
            t_curr = 0
            # level = logging.WARNING
            level = logging.DEBUG

            while True:
                # wait for next agent plan check
                state_msg : AgentStateMessage = await self.states_inbox.get()
                state = SimulationAgentState.from_dict(state_msg.state)

                if self.parent_agent_type is None:
                    if isinstance(state, SatelliteAgentState):
                        # import orbit data
                        self.orbitdata : OrbitData = self.__load_orbit_data()
                        self.parent_agent_type = SimulationAgentTypes.SATELLITE.value
                    
                    elif isinstance(state, UAVAgentState):
                        # TODO Add UAV support
                        raise NotImplementedError(f"states of type {state_msg.state['state_type']} not supported for greedy planners.")
                    
                    else:
                        raise NotImplementedError(f"states of type {state_msg.state['state_type']} not supported for greedy planners.")


                t_curr = state.t
                await self.update_current_time(t_curr)                

                # compare bids with incoming messages
                self.log_results('\nINITIAL RESULTS', results, level)
                self.log_task_sequence('bundle', bundle, level)
                self.log_task_sequence('path', path, level)

                t_0 = time.perf_counter()
                t_curr = state.t
                results, comp_bundle, comp_path, _, comp_rebroadcasts = await self.consensus_phase(results, copy.copy(bundle), copy.copy(path), t_curr, level)
                comp_rebroadcasts : list
                dt = time.perf_counter() - t_0
                self.stats['consensus'].append(dt)

                # self.log_results('BIDS RECEIVED', bids_received, level)
                self.log_results('COMPARED RESULTS', results, level)
                self.log_task_sequence('bundle', comp_bundle, level)
                self.log_task_sequence('path', comp_path, level)

                # determine if bundle was affected by incoming bids
                changes_to_bundle : bool = not self.compare_bundles(bundle, comp_bundle)

                if changes_to_bundle or len(comp_rebroadcasts) > 0:
                    # replan
                    state, results, bundle, path = await self.update_bundle(state, 
                                                                        results, 
                                                                        copy.copy(comp_bundle), 
                                                                        copy.copy(comp_path), 
                                                                        level)
                    # broadcast plan 
                    if not self.compare_bundles(bundle, comp_bundle):
                        for req, subtask_index in bundle:
                            req : MeasurementRequest; subtask_index : int
                            bid : SubtaskBid = results[req.id][subtask_index]
                            bid_change_msg = MeasurementBidMessage(
                                                            self.get_parent_name(),
                                                            self.get_parent_name(),
                                                            bid.to_dict()
                            )
                            comp_rebroadcasts.append(bid_change_msg)
                    await self.bid_broadcaster(comp_rebroadcasts, t_curr, level=level)

                    state : SimulationAgentState
                    t_curr = state.t
                    plan = self.plan_from_path(state, results, path)
                    self.log_plan(results, plan, t_curr, level)

                    # log plan
                    measurement_plan = []   
                    for action in plan:
                        if isinstance(action, MeasurementAction):
                            measurement_req = MeasurementRequest.from_dict(action.measurement_req)
                            subtask_index : int = action.subtask_index
                            subtask_bid : SubtaskBid = results[measurement_req.id][subtask_index]  
                            measurement_plan.append((t_curr, measurement_req, subtask_index, subtask_bid.copy()))
                    self.plan_history.append(measurement_plan)

                # execute plan
                t_0 = time.perf_counter()
                comp_bundle, comp_path, plan, next_actions = await self.get_next_actions( copy.copy(bundle), copy.copy(path), plan, prev_actions, t_curr)
                
                # determine if bundle was affected by executing a task from the plan
                changes_to_bundle : bool = not self.compare_bundles(bundle, comp_bundle)
                
                if not changes_to_bundle: 
                    # continue plan execution
                    await self.action_broadcaster(next_actions)
                    dt = time.perf_counter() - t_0
                    self.stats['doing'].append(dt)
                    prev_actions = next_actions                

                else:                  
                    # replan
                    state, results, bundle, path = await self.update_bundle(state, 
                                                                        results, 
                                                                        comp_bundle, 
                                                                        comp_path, 
                                                                        level)
                    
                    plan = self.plan_from_path(state, results, path)
                    self.log_plan(results, plan, state.t, level)

                    # broadcast plan 
                    comp_rebroadcasts = []
                    for req, subtask_index in bundle:
                        req : MeasurementRequest; subtask_index : int
                        bid : SubtaskBid = results[req.id][subtask_index]
                        bid_change_msg = MeasurementBidMessage(
                                                        self.get_parent_name(),
                                                        self.get_parent_name(),
                                                        bid.to_dict()
                        )
                        comp_rebroadcasts.append(bid_change_msg)
                    await self.bid_broadcaster(comp_rebroadcasts, t_curr, level=level)

                    # log plan
                    measurement_plan = []
                    for action in plan:
                        if isinstance(action, MeasurementAction):
                            measurement_req = MeasurementRequest.from_dict(action.measurement_req)
                            subtask_index : int = action.subtask_index
                            subtask_bid : SubtaskBid = results[measurement_req.id][subtask_index]  
                            measurement_plan.append((t_curr, measurement_req, subtask_index, subtask_bid.copy()))
                    self.plan_history.append(measurement_plan)

                    # execute plan
                    t_0 = time.perf_counter()
                    comp_bundle, comp_path, plan, next_actions = await self.get_next_actions( copy.copy(bundle), copy.copy(path), plan, [], t_curr)

                    await self.action_broadcaster(next_actions)
                    dt = time.perf_counter() - t_0
                    self.stats['doing'].append(dt)
                    prev_actions = next_actions   
                                
        except asyncio.CancelledError:
            return 
        
        except Exception as e:
            raise e

    

    async def update_bundle(    self, 
                                state : SimulationAgentState, 
                                results : dict, 
                                bundle : list, 
                                path : list, 
                                level : int = logging.DEBUG
                            ) -> tuple:
        """
        Runs ACCBBA planning-consensus phases and creates a plan to be executed by agents 
        """
        converged = False
        self.iter_counter = -1
        level = logging.WARNING

        while True:
            # Phase 2: Consensus 
            t_0 = time.perf_counter()
            t_curr = state.t
            results, bundle, path, consensus_changes, consensus_rebroadcasts = await self.consensus_phase(results, bundle, path, t_curr, level)
            dt = time.perf_counter() - t_0
            self.stats['consensus'].append(dt)

            # Update iteration counter
            self.iter_counter += 1

            # Phase 1: Create Plan from latest information
            t_0 = time.perf_counter()
            results, bundle, path, planner_changes = await self.planning_phase(state, results, bundle, path, level)
            dt = time.perf_counter() - t_0
            self.stats['planning'].append(dt)

            if len(bundle) > 0:
                x = 1

            self.log_changes("CHANGES MADE FROM PLANNING", planner_changes, level)
            self.log_changes("CHANGES MADE FROM CONSENSUS", consensus_changes, level)

            # Check for convergence
            if converged:
                break
            converged = self.path_constraint_sat(path, results, t_curr)

            # Broadcast changes to bundle and any changes from consensus
            broadcast_bids : list = consensus_rebroadcasts
            broadcast_bids.extend(planner_changes)
            self.log_changes("REBROADCASTS TO BE DONE", broadcast_bids, level)
            wait_for_response = self.has_bundle_dependencies(bundle) and not converged
            await self.bid_broadcaster(broadcast_bids, t_curr, wait_for_response, level)
            
            # Update State
            state_msg : AgentStateMessage = await self.states_inbox.get()
            state = SimulationAgentState.from_dict(state_msg.state)
            t_curr = state.t
            await self.update_current_time(t_curr)  

        # level = logging.WARNING
        self.log_results('PLAN CREATED', results, level)
        self.log_task_sequence('Bundle', bundle, level)
        self.log_task_sequence('Path', path, level)
        
        # reset planning counters
        for task_id in results:
            for subtask_index in range(len(results[task_id])):
                bid : SubtaskBid = results[task_id][subtask_index]
                bid.reset_bid_counters()
                results[task_id][subtask_index] = bid

        return state, results, bundle, path
      

    

    
    async def get_next_actions(self, bundle : list, path : list, plan : list, prev_actions : list, t_curr : Union[int, float]) -> None:
        """
        A plan has already been developed and is being performed; check plan complation status
        """
        actions = []

        if len(prev_actions) == 0:
            if len(plan) > 0:
                next_task : AgentAction = plan[0]
                if t_curr >= next_task.t_start:
                    actions.append(next_task)
                else:
                    actions.append( WaitForMessages(t_curr, next_task.t_start) )
        
        else:
            if self.action_status_inbox.empty():
                # wait for task completion statuses to arrive from parent agent
                await self.action_status_inbox.put(await self.action_status_inbox.get())

            while not self.action_status_inbox.empty():
                action_msg : AgentActionMessage = await self.action_status_inbox.get()
                performed_action = AgentAction(**action_msg.action)
                self.log(f'Reveived action status for action of type {performed_action.action_type}!', level=logging.DEBUG)

                if len(plan) < 1:
                    continue

                latest_plan_action : AgentAction = plan[0]
                if performed_action.id != latest_plan_action.id:
                    # some other task was performed; ignoring 
                    self.log(f'Action of type {performed_action.action_type} was not part of original plan. Ignoring completion status.', level=logging.DEBUG)
                    continue

                elif performed_action.status == AgentAction.PENDING:
                    # latest action from plan was attepted but not completed; performing again
                    
                    if t_curr < performed_action.t_start:
                        # if action was not ready to be performed, wait for a bit
                        self.log(f'Action of type {performed_action.action_type} was attempted before its start time. Waiting for a bit...', level=logging.DEBUG)
                        actions.append( WaitForMessages(t_curr, performed_action.t_start) )
                    else:
                        # try to perform action again
                        self.log(f'Action of type {performed_action.action_type} was attempted but not completed. Trying again...', level=logging.DEBUG)
                        actions.append(plan[0])

                elif performed_action.status == AgentAction.COMPLETED or performed_action.status == AgentAction.ABORTED:
                    # latest action from plan was completed! performing next action in plan
                    done_action : AgentAction = plan.pop(0)
                    self.log(f'Completed action of type {done_action.action_type}!', level=logging.DEBUG)

                    if done_action.action_type == ActionTypes.MEASURE.value:
                        done_action : MeasurementAction
                        done_task = MeasurementRequest.from_dict(done_action.measurement_req)
                        
                        # if a measurement action was completed, remove from bundle and path
                        if (done_task, done_action.subtask_index) in path:
                            path.remove((done_task, done_action.subtask_index))
                            bundle.remove((done_task, done_action.subtask_index))

                    if len(plan) > 0:
                        next_task : AgentAction = plan[0]
                        if t_curr >= next_task.t_start:
                            actions.append(next_task)
                        else:
                            actions.append( WaitForMessages(t_curr, next_task.t_start) )
        
        if len(actions) == 0:
            if len(plan) > 0:
                next_task : AgentAction = plan[0]
                if t_curr >= next_task.t_start:
                    actions.append(next_task)
                else:
                    actions.append( WaitForMessages(t_curr, next_task.t_start) )
        
            else:
                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    if self.parent_agent_type == SimulationAgentTypes.SATELLITE.value:
                        actions.append( WaitForMessages(t_curr, t_curr + self.orbitdata.time_step) )
                    else:
                        actions.append( WaitForMessages(t_curr, t_curr + self._clock_config.get_time_step()) )

                elif isinstance(self._clock_config, EventDrivenClockConfig):
                    if self.parent_agent_type == SimulationAgentTypes.SATELLITE.value:
                        # t_next_gp = self.orbitdata.get_next_gp_access_interval()
                        t_next = np.Inf 
                    else:
                        t_next = np.Inf 
                    actions.append( WaitForMessages(t_curr, t_next) )
                else:
                    actions.append( WaitForMessages(t_curr, t_curr + 1) )

        return bundle, path, plan, actions

    async def bid_broadcaster(self, bids : list, t_curr : Union[int, float], wait_for_response : bool = False, level : int = logging.DEBUG) -> None:
        """
        Sends bids to parent agent for broadcasting. Only sends the most recent bid of a particular task.

        ### Arguments:
            - bids (`list`): bids to be broadcasted
        """
        if len(bids) == 0 :
            x = 1

        bid_messages = {}
        for msg in bids:
            msg : MeasurementBidMessage
            bundle_bid : SubtaskBid = SubtaskBid(**msg.bid)
            if bundle_bid.req_id not in bid_messages:
                bid_messages[bundle_bid.req_id] = {bundle_bid.subtask_index : msg}

            elif bundle_bid.subtask_index not in bid_messages[bundle_bid.req_id]:
                bid_messages[bundle_bid.req_id][bundle_bid.subtask_index] = msg
                
            else:
                # only keep most recent information for bids
                listener_bid_msg : MeasurementBidMessage = bid_messages[bundle_bid.req_id][bundle_bid.subtask_index]
                listener_bid : SubtaskBid = SubtaskBid(**listener_bid_msg.bid)
                if bundle_bid.t_update >= listener_bid.t_update:
                    bid_messages[bundle_bid.req_id][bundle_bid.subtask_index] = msg

        # build plan
        plan = []
        changes = []
        for req_id in bid_messages:
            for subtask_index in bid_messages[req_id]:
                bid_message : MeasurementBidMessage = bid_messages[req_id][subtask_index]
                changes.append(bid_message)
                plan.append(BroadcastMessageAction(bid_message.to_dict(), t_curr).to_dict())
        
        if wait_for_response:
            plan.append(WaitForMessages(t_curr, t_curr + 1).to_dict())
        
        # send to agent
        self.log(f'bids compared! generating plan with {len(bid_messages)} bid messages')
        plan_msg = PlanMessage(self.get_element_name(), self.get_parent_name(), plan)
        await self._send_manager_msg(plan_msg, zmq.PUB)
        self.log(f'actions sent!')

        # wait for tasks to be completed
        plan_ids = [action['id'] for action in plan]
        misc_action_msgs = []
        while len(plan_ids) > 0:
            action_msg : AgentActionMessage = await self.action_status_inbox.get()
            action_completed = AgentAction(**action_msg.action)

            if action_completed.id in plan_ids:
                plan_ids.remove(action_completed.id)
            
            else:
                misc_action_msgs.append(action_msg)

        for action_msg in misc_action_msgs:
            await self.action_status_inbox.put(action_msg)

        self.log_changes("BROADCASTS SENT", changes, level)

    async def action_broadcaster(self, next_actions : list) -> None:
        """
        Sends the parent agent a list of actions to be performed
        """
        # generate plan dictionaries for transmission
        actions_dict = [action.to_dict() for action in next_actions]

        # send plan to agent
        self.log(f'bids compared! generating plan with {len(next_actions)} action(s).')
        plan_msg = PlanMessage(self.get_element_name(), self.get_parent_name(), actions_dict)
        await self._send_manager_msg(plan_msg, zmq.PUB)
        self.log(f'actions sent!')

        self.log(f'plan sent {[action.action_type for action in next_actions]}', level=logging.DEBUG)


    # LOGGING TOOLS
    
    
    