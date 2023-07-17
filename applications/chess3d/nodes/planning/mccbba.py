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

class SubtaskBid(Bid):
    """
    ## Subtask Bid for ACBBA 

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - req (`dict`): task being bid on
        - req_id (`str`): id of the task being bid on
        - subtask_index (`int`) : index of the subtask to be bid on
        - main_measurement (`str`): name of the main measurement assigned by this subtask bid
        - dependencies (`list`): portion of the dependency matrix related to this subtask bid
        - time_constraints (`list`): portion of the time dependency matrix related to this subtask bid
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
        - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
        - t_violation (`float` or `int`): time from which this task bid has been in violation of its constraints
        - dt_violoation (`float` or `int`): maximum time in which this bid is allowed to be in violation of its constraints
        - bid_solo (`int`): maximum number of solo bid attempts with no constraint satisfaction attempts
        - bid_any (`int`): maximum number of bid attempts with partial constraint satisfaction attempts
        - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
    """      
    def __init__(
                    self, 
                    req: dict, 
                    subtask_index : int,
                    main_measurement : str,
                    dependencies : list,
                    time_constraints : list,
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = Bid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    dt_converge: Union[float, int] = 0.0, 
                    t_violation: Union[float, int] = -1, 
                    dt_violoation: Union[float, int] = 0.0,
                    bid_solo : int = 1,
                    bid_any : int = 1, 
                    performed : bool = False,
                    **_
                ) -> object:
        """
        Creates an instance of a task bid

        ### Arguments:
            - task (`dict`): task being bid on
            - subtask_index (`int`) : index of the subtask to be bid on
            - main_measurement (`str`): name of the main measurement assigned by this subtask bid
            - dependencies (`list`): portion of the dependency matrix related to this subtask bid
            - time_constraints (`list`): portion of the time dependency matrix related to this subtask bid
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
            - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
            - t_violation (`float` or `int`): time from which this task bid has been in violation of its constraints
            - dt_violoation (`float` or `int`): maximum time in which this bid is allowed to be in violation of its constraints
            - bid_solo (`int`): maximum number of solo bid attempts with no constraint satisfaction attempts
            - bid_any (`int`): maximum number of bid attempts with partial constraint satisfaction attempts
            - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
        """
        super().__init__(req, bidder, winning_bid, own_bid, winner, t_img, t_update)

        self.subtask_index = subtask_index
        self.main_measurement = main_measurement
        self.dependencies = dependencies
        
        self.N_req = 0
        for dependency in dependencies:
            if dependency > 0:
                self.N_req += 1

        self.time_constraints = time_constraints
        self.t_violation = t_violation
        self.dt_violation = dt_violoation
        
        if not isinstance(bid_solo, int):
            raise ValueError(f'`bid_solo` must be of type `int`. Is of type {type(bid_solo)}')
        elif bid_solo < 0:
            raise ValueError(f'`bid_solo` must be a positive `int`. Was given value of {bid_solo}.')
        self.bid_solo = bid_solo
        self.bid_solo_max = bid_solo

        if not isinstance(bid_any, int):
            raise ValueError(f'`bid_solo` must be of type `int`. Is of type {type(bid_any)}')
        elif bid_any < 0:
            raise ValueError(f'`bid_solo` must be a positive `int`. Was given value of {bid_any}.')
        self.bid_any = bid_any
        self.bid_any_max = bid_any
        self.dt_converge = dt_converge
        self.performed = performed

    def update(self, other_dict : dict, t : Union[float, int]) -> tuple:
        broadcast_out, changed = self.__update_rules(other_dict, t)
        broadcast_out : Bid; changed : bool

        if broadcast_out is not None:
            other = SubtaskBid(**other_dict)
            if other.bidder == broadcast_out.bidder:
                return other, changed
            else:
                return self, changed
        return None, changed

    def __update_rules(self, other_dict : dict, t : Union[float, int]) -> tuple:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:
            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." Proceedings of the 2011 American Control Conference. IEEE, 2011.

        ### Arguments:
            - other_dict (`dict`): dictionary representing the bid being compared to
            - t (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): bid information to be rebroadcasted to other agents.
            - changed (`bool`): boolean value indicating if a change was made to this bid
        """
        other : SubtaskBid = SubtaskBid(**other_dict)
        prev : SubtaskBid = self.copy() 

        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        if other.bidder == self.bidder:
            if other.t_update > self.t_update:
                self._update_info(other,t)
                return self, prev==self
            else:
                self._leave(t)
                return None, False
        
        elif other.winner == other.NONE:
            if self.winner == self.bidder:
                # leave and rebroadcast
                self._leave(t)
                return self, False

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev==self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                self._leave(t)
                return None, False

        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self
                    
                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev==self

                if other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return self, prev==self

            elif self.winner == other.bidder:
                if other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

                elif other.t_update < self.t_update:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    #leave and rebroadcast
                    self._leave(t)
                    return self, False

                elif other.winning_bid == self.winning_bid:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False

                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev==self

        elif other.winner == self.bidder:
            if self.winner == self.NONE:
                # leave and rebroadcast with current update time
                self.__update_time(t)
                return self, prev==self

            elif self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False
                
            elif self.winner == other.bidder and other.bidder != self.bidder:
                # reset and rebroadcast with current update time
                self.reset(t)
                return self, prev==self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                # leave and rebroadcast
                self._leave(t)
                return self, False

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev==self

                elif other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return other, prev==self

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev==self

            elif self.winner == other.winner:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self
                    
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

                elif other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False

            elif self.winner not in [self.bidder, other.bidder, other.winner, self.NONE]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False
                    
                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev==self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, prev==self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev==self
        
        return None, prev==self

    def set_bid(self, new_bid : Union[int, float], t_img : Union[int, float], t_update : Union[int, float]) -> None:
        """
        Sets new values for this bid

        ### Arguments: 
            - new_bid (`int` or `float`): new bid value
            - t_img (`int` or `float`): new imaging time
            - t_update (`int` or `float`): update time
        """
        self.own_bid = new_bid
        self.winning_bid = new_bid
        self.winner = self.bidder
        self.t_img = t_img
        self.t_violation = -1
        self.t_update = t_update

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `subtask_index`, `main_measurement`, `dependencies`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`, `t_update`
        """
        req : MeasurementRequest = MeasurementRequest.from_dict(self.req)
        split_id = req.id.split('-')
        line_data = [split_id[0], self.subtask_index, self.main_measurement, self.dependencies, req.lat_lon_pos, self.bidder, round(self.own_bid, 3), self.winner, round(self.winning_bid, 3), round(self.t_img, 3), round(self.t_violation, 3), self.bid_solo, self.bid_any]
        out = ""
        for i in range(len(line_data)):
            line_datum = line_data[i]
            out += str(line_datum)
            if i < len(line_data) - 1:
                out += ','

        return out
    
    def reset_bid_counters(self) -> None:
        """
        Resets this bid's bid counters for optimistic bidding strategies when replanning
        """
        self.bid_solo = self.bid_solo_max
        self.bid_any = self.bid_any_max

    def copy(self) -> object:
        return SubtaskBid(  **self.to_dict() )

    def subtask_bids_from_task(task : MeasurementRequest, bidder : str) -> list:
        """
        Generates subtask bids from a measurement task request
        """
        subtasks = []        
        for subtask_index in range(len(task.measurement_groups)):
            main_measurement, _ = task.measurement_groups[subtask_index]
            subtasks.append(SubtaskBid( task.to_dict(), 
                                        subtask_index,
                                        main_measurement,
                                        task.dependency_matrix[subtask_index],
                                        task.time_dependency_matrix[subtask_index],
                                        bidder))
        return subtasks

    def reset(self, t_update: Union[float, int]) -> None:
        # reset violation timer
        self.__reset_violation_timer(t_update)
        
        # reset bid values
        super().reset(t_update)        

    def has_winner(self) -> bool:
        """
        Checks if this bid has a winner
        """
        return self.winner != Bid.NONE

    def _update_info(self, 
                    other, 
                    t : Union[float, int]
                    ) -> None:
        """
        Updates all of the variable bid information

        ### Arguments:
            - other (`TaskBid`): equivalent bid being used to update information
            - t (`float` or `dict`): time when this information is being updated
        """
        if t < self.t_update:
            # if update is from an older time than this bid, ignore update
            raise ValueError(f'attempting to update bid with outdated information.')

        super()._update_info(other)
        self.__update_time(t)
        self.performed = other.performed

    def __update_time(self, t_update : Union[float, int]) -> None:
        """
        Only updates the time since this bid was last updated

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        self.t_update = t_update

    def __set_violation_timer(self, t : Union[int, float]) -> None:
        """
        Updates violation counter
        """
        if self.t_violation < 0:
            self.t_violation = t 

    def __reset_violation_timer(self, t : Union[int, float]) -> None:
        """
        Resets violation counter
        """
        if self.winner == self.bidder:
            self.t_violation = -1

    def is_optimistic(self) -> bool:
        """
        Checks if bid has an optimistic bidding strategy
        """
        for dependency in self.dependencies:
            if dependency > 0:
                return True

        return False   

    def __has_timed_out(self, t : Union[int, float]) -> bool:
        """
        Returns True if the subtask's constraint violation timer has ran out.    
        """
        if self.t_violation < 0:
            return False

        return t >= self.dt_violation + self.t_violation
    

    def count_coal_conts_satisied(self, others : list) -> int:
        """
        Counts the total number of satisfied coalition constraints
        """
        if len(others) != len(self.dependencies):
            raise ValueError(f'`others` list must be of length {len(self.dependencies)}. is of length {len(others)}')
        
        n_sat = 0
        for i in range(len(others)):
            other_bid : SubtaskBid = others[i]
            if self.dependencies[i] == 1 and other_bid.winner != SubtaskBid.NONE:
                n_sat += 1
        
        return n_sat 

    def check_constraints(self, others : list, t : Union[int, float]) -> tuple:
        """
        Compares current bid to other bids for the same task but different subtasks and checks for constraint satisfaction
        
        ### Arguments:
            - others (`list`): list of all subtasks bids from the same task
            -  (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): returns bid information to be rebroadcasted to other agents.
        """
        mutex_sat = self.__mutex_sat(others, t)
        dep_sat = self.__dep_sat(others, t)
        temp_sat, const_failed = self.__temp_sat(others, t)

        if not mutex_sat or not dep_sat or not temp_sat:
            if self.is_optimistic():
                self.bid_any -= 1
                self.bid_any = self.bid_any if self.bid_any > 0 else 0

                self.bid_solo -= 1
                self.bid_solo = self.bid_solo if self.bid_solo >= 0 else 0
            
            return self, const_failed

        return None, None

    def __mutex_sat(self, others : list, _ : Union[int, float]) -> bool:
        """
        Checks for mutually exclusive dependency satisfaction
        """
        # calculate total agent bid count
        agent_bid = self.winning_bid
        agent_coalition = [self.subtask_index]
        for bid_i in others:
            bid_i : SubtaskBid
            bid_i_index = others.index(bid_i)

            if bid_i_index == self.subtask_index:
                continue

            if self.dependencies[bid_i_index] == 1:
                agent_bid += bid_i.winning_bid
                agent_coalition.append(bid_i_index)

        # initiate coalition bid count
        ## find all possible coalitions
        task = MeasurementRequest.from_dict(self.req)
        possible_coalitions = []
        for i in range(len(task.dependency_matrix)):
            coalition = [i]
            for j in range(len(task.dependency_matrix[i])):
                if task.dependency_matrix[i][j] == 1:
                    coalition.append(j)
            possible_coalitions.append(coalition)
        
        # calculate total mutex bid count
        max_mutex_bid = 0
        for coalition in possible_coalitions:
            mutex_bid = 0
            for coalition_member in coalition:
                bid_i : SubtaskBid = others[coalition_member]

                if self.subtask_index == coalition_member:
                    continue
                
                is_mutex = True
                for agent_coalition_member in agent_coalition:
                  if task.dependency_matrix[coalition_member][agent_coalition_member] >= 0:
                    is_mutex = False  
                    break

                if not is_mutex:
                    break
                
                mutex_bid += bid_i.winning_bid

            max_mutex_bid = max(mutex_bid, max_mutex_bid)

        return agent_bid > max_mutex_bid

    def __dep_sat(self, others : list, t : Union[int, float]) -> bool:
        """
        Checks for dependency constraint satisfaction
        """
        n_sat = self.count_coal_conts_satisied(others)
        if self.is_optimistic():
            if self.N_req > n_sat:
                self.__set_violation_timer(t)    
            else:
                self.__reset_violation_timer(t)
            return not self.__has_timed_out(t)
        else:
            return self.N_req == n_sat


    def __temp_sat(self, others : list, t : Union[int, float]) -> bool:
        """
        Checks for temporal constraint satisfaction
        """
        for other in others:
            other : SubtaskBid
            if other.winner == SubtaskBid.NONE:
                continue

            corr_time_met = (self.t_img <= other.t_img + self.time_constraints[other.subtask_index]
                            and other.t_img <= self.t_img + other.time_constraints[self.subtask_index])
            
            independent = other.dependencies[self.subtask_index] <= 0

            # tie_breaker = self.is_optimistic() and (self.t_img > other.t_img)

            # if not corr_time_met and not independent and not tie_breaker:
            if not corr_time_met and not independent:
                return False, other
        
        return True, None

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

    def __load_orbit_data(self) -> OrbitData:
        if self.parent_agent_type != None:
            raise RuntimeError(f"orbit data already loaded. It can only be assigned once.")            

        scenario_name = self.results_path.split('/')[-1]
        scenario_dir = f'./scenarios/{scenario_name}/'
        data_dir = scenario_dir + '/orbitdata/'

        with open(scenario_dir + '/MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict : dict = json.load(scenario_specs)
            spacecraft_list : list = mission_dict.get('spacecraft', None)
            ground_station_list = mission_dict.get('groundStation', None)
            
            for spacecraft in spacecraft_list:
                spacecraft : dict
                name = spacecraft.get('name')
                index = spacecraft_list.index(spacecraft)
                agent_folder = "sat" + str(index) + '/'

                if name != self.get_parent_name():
                    continue

                # load eclipse data
                eclipse_file = data_dir + agent_folder + "eclipses.csv"
                eclipse_data = pd.read_csv(eclipse_file, skiprows=range(3))
                
                # load position data
                position_file = data_dir + agent_folder + "state_cartesian.csv"
                position_data = pd.read_csv(position_file, skiprows=range(4))

                # load propagation time data
                time_data =  pd.read_csv(position_file, nrows=3)
                _, epoc_type, _, epoc = time_data.at[0,time_data.axes[1][0]].split(' ')
                epoc_type = epoc_type[1 : -1]
                epoc = float(epoc)
                _, _, _, _, time_step = time_data.at[1,time_data.axes[1][0]].split(' ')
                time_step = float(time_step)

                time_data = { "epoc": epoc, 
                            "epoc type": epoc_type, 
                            "time step": time_step }

                # load inter-satellite link data
                isl_data = dict()
                for file in os.listdir(data_dir + '/comm/'):                
                    isl = re.sub(".csv", "", file)
                    sender, _, receiver = isl.split('_')

                    if 'sat' + str(index) in sender or 'sat' + str(index) in receiver:
                        isl_file = data_dir + 'comm/' + file
                        if 'sat' + str(index) in sender:
                            receiver_index = int(re.sub("[^0-9]", "", receiver))
                            receiver_name = spacecraft_list[receiver_index].get('name')
                            isl_data[receiver_name] = pd.read_csv(isl_file, skiprows=range(3))
                        else:
                            sender_index = int(re.sub("[^0-9]", "", sender))
                            sender_name = spacecraft_list[sender_index].get('name')
                            isl_data[sender_name] = pd.read_csv(isl_file, skiprows=range(3))

                # load ground station access data
                gs_access_data = pd.DataFrame(columns=['start index', 'end index', 'gndStn id', 'gndStn name','lat [deg]','lon [deg]'])
                for file in os.listdir(data_dir + agent_folder):
                    if 'gndStn' in file:
                        gndStn_access_file = data_dir + agent_folder + file
                        gndStn_access_data = pd.read_csv(gndStn_access_file, skiprows=range(3))
                        nrows, _ = gndStn_access_data.shape

                        if nrows > 0:
                            gndStn, _ = file.split('_')
                            gndStn_index = int(re.sub("[^0-9]", "", gndStn))
                            
                            gndStn_name = ground_station_list[gndStn_index].get('name')
                            gndStn_id = ground_station_list[gndStn_index].get('@id')
                            gndStn_lat = ground_station_list[gndStn_index].get('latitude')
                            gndStn_lon = ground_station_list[gndStn_index].get('longitude')

                            gndStn_name_column = [gndStn_name] * nrows
                            gndStn_id_column = [gndStn_id] * nrows
                            gndStn_lat_column = [gndStn_lat] * nrows
                            gndStn_lon_column = [gndStn_lon] * nrows

                            gndStn_access_data['gndStn name'] = gndStn_name_column
                            gndStn_access_data['gndStn id'] = gndStn_id_column
                            gndStn_access_data['lat [deg]'] = gndStn_lat_column
                            gndStn_access_data['lon [deg]'] = gndStn_lon_column

                            if len(gs_access_data) == 0:
                                gs_access_data = gndStn_access_data
                            else:
                                gs_access_data = pd.concat([gs_access_data, gndStn_access_data])

                # land coverage data metrics data
                payload = spacecraft.get('instrument', None)
                if not isinstance(payload, list):
                    payload = [payload]

                gp_access_data = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]', 'agent','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                for instrument in payload:
                    i_ins = payload.index(instrument)
                    gp_acces_by_mode = []

                    # modes = spacecraft.get('instrument', None)
                    # if not isinstance(modes, list):
                    #     modes = [0]
                    modes = [0]

                    gp_acces_by_mode = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])
                    for mode in modes:
                        i_mode = modes.index(mode)
                        gp_access_by_grid = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                        for grid in mission_dict.get('grid'):
                            i_grid = mission_dict.get('grid').index(grid)
                            metrics_file = data_dir + agent_folder + f'datametrics_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                            metrics_data = pd.read_csv(metrics_file, skiprows=range(4))
                            
                            nrows, _ = metrics_data.shape
                            grid_id_column = [i_grid] * nrows
                            metrics_data['grid index'] = grid_id_column

                            if len(gp_access_by_grid) == 0:
                                gp_access_by_grid = metrics_data
                            else:
                                gp_access_by_grid = pd.concat([gp_access_by_grid, metrics_data])

                        nrows, _ = gp_access_by_grid.shape
                        gp_access_by_grid['pnt-opt index'] = [mode] * nrows

                        if len(gp_acces_by_mode) == 0:
                            gp_acces_by_mode = gp_access_by_grid
                        else:
                            gp_acces_by_mode = pd.concat([gp_acces_by_mode, gp_access_by_grid])
                        # gp_acces_by_mode.append(gp_access_by_grid)

                    nrows, _ = gp_acces_by_mode.shape
                    gp_access_by_grid['instrument'] = [instrument] * nrows
                    # gp_access_data[ins_name] = gp_acces_by_mode

                    if len(gp_access_data) == 0:
                        gp_access_data = gp_acces_by_mode
                    else:
                        gp_access_data = pd.concat([gp_access_data, gp_acces_by_mode])
                
                nrows, _ = gp_access_data.shape
                gp_access_data['agent name'] = [spacecraft['name']] * nrows

                grid_data_compiled = []
                for grid in mission_dict.get('grid'):
                    i_grid = mission_dict.get('grid').index(grid)
                    grid_file = data_dir + f'grid{i_grid}.csv'

                    grid_data = pd.read_csv(grid_file)
                    nrows, _ = grid_data.shape
                    grid_data['GP index'] = [i for i in range(nrows)]
                    grid_data['grid index'] = [i_grid] * nrows
                    grid_data_compiled.append(grid_data)

                return OrbitData(name, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data, grid_data_compiled)


    def compare_bundles(self, bundle_1 : list, bundle_2 : list) -> bool:
        """
        Compares two bundles. Returns true if they are equal and false if not.
        """
        if len(bundle_1) == len(bundle_2):
            for req, subtask in bundle_1:
                if (req, subtask) not in bundle_2:            
                    return False
            return True
        return False

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
    
    async def consensus_phase(  
                                self, 
                                results : dict, 
                                bundle : list, 
                                path : list, 
                                t : Union[int, float], 
                                new_bids : list,
                                level : int = logging.DEBUG
                            ) -> None:
        """
        Evaluates incoming bids and updates current results and bundle
        """
        changes = []
        rebroadcasts = []
        self.log_results('\nINITIAL RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)
        
        # compare bids with incoming messages
        t_0 = time.perf_counter()
        results, bundle, path, comp_changes, comp_rebroadcasts = await self.compare_results(results, bundle, path, t, new_bids, level)
        changes.extend(comp_changes)
        rebroadcasts.extend(comp_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_comp_check'].append(dt)

        self.log_results('BIDS RECEIVED', new_bids, level)
        self.log_results('COMPARED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)
        
        # check for expired tasks
        t_0 = time.perf_counter()
        results, bundle, path, exp_changes, exp_rebroadcasts = await self.check_request_end_time(results, bundle, path, t, level)
        changes.extend(exp_changes)
        rebroadcasts.extend(exp_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check for already performed tasks
        t_0 = time.perf_counter()
        results, bundle, path, done_changes, done_rebroadcasts = await self.check_request_completion(results, bundle, path, t, level)
        changes.extend(done_changes)
        rebroadcasts.extend(done_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check task constraint satisfaction
        t_0 = time.perf_counter()
        results, bundle, path, cons_changes, cons_rebroadcasts = await self.check_bid_constraints(results, bundle, path, t, level)
        changes.extend(cons_changes)
        rebroadcasts.extend(cons_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_const_check'].append(dt)

        self.log_results('CONSTRAINT CHECKED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes, rebroadcasts
    
    def compare_results(
                        self, 
                        results : dict, 
                        bundle : list, 
                        path : list, 
                        t : Union[int, float], 
                        new_bids : list,
                        level=logging.DEBUG
                    ) -> tuple:
        """
        Compares the existing results with any incoming task bids and updates the bundle accordingly

        ### Returns
            - results
            - bundle
            - path
            - changes
        """
        changes = []
        rebroadcasts = []

        for their_bid in new_bids:
            their_bid : SubtaskBid            

            # check bids are for new requests
            new_req = their_bid.req_id not in results

            if new_req:
                # was not aware of this request; add to results as a blank bid
                req = MeasurementRequest.from_dict(their_bid.req)
                results[req.id] = SubtaskBid.subtask_bids_from_task(req, self.get_parent_name())

                # add to changes broadcast
                my_bid : SubtaskBid = results[req.id][0]
                rebroadcasts.append(my_bid)
                                    
            # compare bids
            my_bid : SubtaskBid = results[their_bid.req_id][their_bid.subtask_index]
            self.log(f'comparing bids...\nmine:  {str(my_bid)}\ntheirs: {str(their_bid)}', level=logging.DEBUG)

            broadcast_bid, changed  = my_bid.update(their_bid.to_dict(), t)
            broadcast_bid : SubtaskBid; changed : bool

            self.log(f'\nupdated: {my_bid}\n', level=logging.DEBUG)
            results[their_bid.req_id][their_bid.subtask_index] = my_bid
                
            # if relevant changes were made, add to changes and rebroadcast
            if changed or new_req:
                changed_bid : SubtaskBid = broadcast_bid if not new_req else my_bid
                changes.append(changed_bid)

            if broadcast_bid or new_req:                    
                broadcast_bid : SubtaskBid = broadcast_bid if not new_req else my_bid
                rebroadcasts.append(broadcast_bid)

            # if outbid for a task in the bundle, release subsequent tasks in bundle and path
            if (
                (req, my_bid.subtask_index) in bundle 
                and my_bid.winner != self.get_parent_name()
                ):
                bid_index = bundle.index((req, my_bid.subtask_index))

                for _ in range(bid_index, len(bundle)):
                    # remove all subsequent tasks from bundle
                    measurement_req, subtask_index = bundle.pop(bid_index)
                    measurement_req : MeasurementRequest
                    path.remove((measurement_req, subtask_index))

                    # if the agent is currently winning this bid, reset results
                    current_bid : SubtaskBid = results[measurement_req.id][subtask_index]
                    if current_bid.winner == self.get_parent_name():
                        current_bid.reset(t)
                        results[measurement_req.id][subtask_index] = current_bid

                        rebroadcasts.append(current_bid)
                        changes.append(current_bid)
        
        return results, bundle, path, changes, rebroadcasts

    async def check_request_end_time(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
        """
        Checks if measurement requests have expired and can no longer be performed

        ### Returns
            - results
            - bundle
            - path
            - changes
        """
        changes = []
        rebroadcasts = []
        # release tasks from bundle if t_end has passed
        task_to_remove = None
        for req, subtask_index in bundle:
            req : MeasurementRequest
            if req.t_end - req.duration < t:
                task_to_remove = (req, subtask_index)
                break

        if task_to_remove is not None:
            bundle_index = bundle.index(task_to_remove)
            for _ in range(bundle_index, len(bundle)):
                # remove all subsequent bids from bundle
                measurement_req, subtask_index = bundle.pop(bundle_index)

                # remove bids from path
                path.remove((measurement_req, subtask_index))

                # if the agent is currently winning this bid, reset results
                measurement_req : SubtaskBid
                current_bid : SubtaskBid = results[measurement_req.id][subtask_index]
                if current_bid.winner == self.get_parent_name():
                    current_bid.reset(t)
                    results[measurement_req.id][subtask_index] = current_bid
                    
                    rebroadcasts.append(current_bid)
                    changes.append(current_bid)

        return results, bundle, path, changes, rebroadcasts

    async def check_request_completion(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
        """
        Checks if a subtask or a mutually exclusive subtask has already been performed 

        ### Returns
            - results
            - bundle
            - path
            - changes
        """

        changes = []
        rebroadcasts = []
        task_to_remove = None
        for req, subtask_index in bundle:
            req : MeasurementRequest

            # check if bid has been performed 
            subtask_bid : SubtaskBid = results[req.id][subtask_index]
            if self.bid_completed(req, subtask_bid, t):
                task_to_remove = (req, subtask_index)
                break

            # check if a mutually exclusive bid has been performed
            for subtask_bid in results[req.id]:
                subtask_bid : SubtaskBid

                bids : list = results[req.id]
                bid_index = bids.index(subtask_bid)
                bid : SubtaskBid = bids[bid_index]

                if self.bid_completed(req, bid, t) and req.dependency_matrix[subtask_index][bid_index] < 0:
                    task_to_remove = (req, subtask_index)
                    break   

            if task_to_remove is not None:
                break

        if task_to_remove is not None:
            bundle_index = bundle.index(task_to_remove)
            
            # level=logging.WARNING
            self.log_results('PRELIMINARY PREVIOUS PERFORMER CHECKED RESULTS', results, level)
            self.log_task_sequence('bundle', bundle, level)
            self.log_task_sequence('path', path, level)

            for _ in range(bundle_index, len(bundle)):
                # remove task from bundle and path
                req, subtask_index = bundle.pop(bundle_index)
                path.remove((req, subtask_index))

                bid : SubtaskBid = results[req.id][subtask_index]
                bid.reset(t)
                results[req.id][subtask_index] = bid

                rebroadcasts.append(bid)
                changes.append(bid)

                self.log_results('PRELIMINARY PREVIOUS PERFORMER CHECKED RESULTS', results, level)
                self.log_task_sequence('bundle', bundle, level)
                self.log_task_sequence('path', path, level)

        return results, bundle, path, changes, rebroadcasts

    def bid_completed(self, req : MeasurementRequest, bid : SubtaskBid, t : float) -> bool:
        """
        Checks if a bid has been completed or not
        """
        return (bid.t_img >= 0.0 and bid.t_img + req.duration < t) or bid.performed

    async def check_bid_constraints(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.WARNING) -> tuple:
        """
        Looks for bids that do not have their constraints satisfied
        """
        changes = []       
        rebroadcasts = []   
        while True:
            # find tasks with constraint violations
            task_to_remove = None
            for req, subtask_index in bundle:
                req : MeasurementRequest; subtask_index : int
                bid : SubtaskBid = results[req.id][subtask_index]
               
                reset_bid, const_failed = bid.check_constraints(results[req.id], t)
                const_failed : SubtaskBid
                
                if reset_bid is not None:
                    if bid.is_optimistic():
                        if const_failed is None:
                            task_to_remove = (req, subtask_index)
                            results[req.id][subtask_index] = reset_bid
                            break
                        elif bid.t_img <= const_failed.t_img:
                            task_to_remove = (req, subtask_index)
                            results[req.id][subtask_index] = reset_bid
                            break
                    else:
                        task_to_remove = (req, subtask_index)
                        results[req.id][subtask_index] = reset_bid
                        break
                                
            if task_to_remove is None:
                # all bids satisfy their constraints
                break 

            bundle_index = bundle.index(task_to_remove)
            for _ in range(bundle_index, len(bundle)):
                # remove task from bundle and path
                req, subtask_index = bundle.pop(bundle_index)
                path.remove((req, subtask_index))

                # reset bid
                req : MeasurementRequest
                bid : SubtaskBid = results[req.id][subtask_index]
                bid.reset(t)
                results[req.id][subtask_index] = bid

                # register change in results
                changes.append(bid)
                rebroadcasts.append(bid)

                self.log_results('PRELIMINARY CONSTRAINT CHECKED RESULTS', results, level)
                self.log_task_sequence('bundle', bundle, level)
                self.log_task_sequence('path', path, level)

        return results, bundle, path, changes, rebroadcasts

    def has_bundle_dependencies(self, bundle : list) -> bool:
        """
        Checks if a bundle contains task with dependencies
        """
        for req, subtask_index in bundle:
            req : MeasurementRequest; subtask_index : int
            dependencies = req.dependency_matrix[subtask_index]
            for dependency in dependencies:
                if dependency > 0:
                    return True
        
        return False

    async def planning_phase(self, state : SimulationAgentState, results : dict, bundle : list, path : list, level : int = logging.DEBUG) -> None:
        """
        Uses the most updated results information to construct a path
        """
        self.log_results('INITIAL BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        available_tasks : list = self.get_available_tasks(state, bundle, results)

        if len(available_tasks) > 0:
            x = 1

        changes = []
        changes_to_bundle = []
        
        current_bids = {task.id : {} for task, _ in bundle}
        for req, subtask_index in bundle:
            req : MeasurementRequest
            current_bid : SubtaskBid = results[req.id][subtask_index]
            current_bids[req.id][subtask_index] = current_bid.copy()

        max_path = [(req, subtask_index) for req, subtask_index in path]; 
        max_path_bids = {req.id : {} for req, _ in path}
        for req, subtask_index in path:
            req : MeasurementRequest
            max_path_bids[req.id][subtask_index] = results[req.id][subtask_index]

        max_utility = 0.0
        max_task = -1

        while len(bundle) < self.max_bundle_size and len(available_tasks) > 0 and max_task is not None:                   
            # find next best task to put in bundle (greedy)
            max_task = None 
            max_subtask = None
            for measurement_req, subtask_index in available_tasks:
                # calculate bid for a given available task
                measurement_req : MeasurementRequest
                subtask_index : int
                projected_path, projected_bids, _ = self.calc_path_bid(state, results, path, measurement_req, subtask_index)
                
                # check if path was found
                if projected_path is None:
                    continue
                
                # compare to maximum task
                bid_utility = projected_bids[measurement_req.id][subtask_index].winning_bid
                if (max_task is None 
                    # or projected_path_utility > max_path_utility
                    or bid_utility > max_utility
                    ):

                    # check for cualition and mutex satisfaction
                    proposed_bid : SubtaskBid = projected_bids[measurement_req.id][subtask_index]
                    passed_coalition_test = self.coalition_test(results, proposed_bid)
                    passed_mutex_test = self.mutex_test(results, proposed_bid)
                    if not passed_coalition_test or not passed_mutex_test:
                        # ignore path if proposed bid for any task cannot out-bid current winners
                        continue
                    
                    max_path = projected_path
                    max_task = measurement_req
                    max_subtask = subtask_index
                    max_path_bids = projected_bids
                    max_utility = projected_bids[measurement_req.id][subtask_index].winning_bid

            if max_task is not None:
                # max bid found! place task with the best bid in the bundle and the path
                bundle.append((max_task, max_subtask))
                path = max_path

                # remove bid task from list of available tasks
                available_tasks.remove((max_task, max_subtask))
            
            #  update bids
            for measurement_req, subtask_index in path:
                measurement_req : MeasurementRequest
                subtask_index : int
                new_bid : Bid = max_path_bids[measurement_req.id][subtask_index]
                old_bid : Bid = results[measurement_req.id][subtask_index]

                if old_bid != new_bid:
                    changes_to_bundle.append((measurement_req, subtask_index))

                results[measurement_req.id][subtask_index] = new_bid

            # self.log_results('PRELIMINART MODIFIED BUNDLE RESULTS', results, level)
            # self.log_task_sequence('bundle', bundle, level)
            # self.log_task_sequence('path', path, level)

        # broadcast changes to bundle
        for measurement_req, subtask_index in changes_to_bundle:
            measurement_req : MeasurementRequest
            subtask_index : int

            new_bid = results[measurement_req.id][subtask_index]

            # add to changes broadcast 
            out_msg = MeasurementBidMessage(   
                                    self.get_parent_name(), 
                                    self.get_parent_name(), 
                                    new_bid.to_dict()
                                )
            changes.append(out_msg)

        self.log_results('MODIFIED BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes

    def get_available_tasks(self, state : SimulationAgentState, bundle : list, results : dict) -> list:
        """
        Checks if there are any tasks available to be performed

        ### Returns:
            - list containing all available and bidable tasks to be performed by the parent agent
        """
        available = []
        for task_id in results:
            for subtask_index in range(len(results[task_id])):
                subtaskbid : SubtaskBid = results[task_id][subtask_index]; 
                req = MeasurementRequest.from_dict(subtaskbid.req)

                if self.bundle_contains_mutex_subtasks(bundle, req, subtask_index):
                    continue

                is_biddable = self.can_bid(state, req, subtask_index, results[task_id]) 
                already_in_bundle = (req, subtaskbid.subtask_index) in bundle 
                already_performed = self.request_has_been_performed(results, req, subtask_index, state.t)
                
                if is_biddable and (not already_in_bundle) and (not already_performed):
                    available.append((req, subtaskbid.subtask_index))

        return available

    def can_bid(self, state : SimulationAgentState, req : MeasurementRequest, subtask_index : int, subtaskbids : list) -> bool:
        """
        Checks if an agent has the ability to bid on a measurement task
        """
        # check planning horizon
        if state.t + self.planning_horizon < req.t_start:
            return False

        # check capabilities - TODO: Replace with knowledge graph
        subtaskbid : SubtaskBid = subtaskbids[subtask_index]
        payload_names : list = [instrument.name for instrument in self.payload]
        if subtaskbid.main_measurement not in payload_names:
            return False 

        # check time constraints
        ## Constraint 1: task must be able to be performed during or after the current time
        if req.t_end < state.t:
            return False

        elif isinstance(req, GroundPointMeasurementRequest):
            # check if agent can see the request location
            lat,lon,_ = req.lat_lon_pos
            df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, state.t)
            can_access = False
            if not df.empty:                
                times = df.get('time index')
                for time in times:
                    time *= self.orbitdata.time_step 

                    # if state.t + self.planning_horizon < time:
                    #     continue

                    # elif time < req.t_end:
                    if time < req.t_end:
                        # there exists an access time before the request's availability ends
                        can_access = True
                        break
                
            if not can_access:
                return False
            else:
                x = 1

        ## Constraint 2: coalition constraints
        n_sat = subtaskbid.count_coal_conts_satisied(subtaskbids)
        if subtaskbid.is_optimistic():
            return (    
                        subtaskbid.N_req == n_sat
                    or  subtaskbid.bid_solo > 0
                    or  (subtaskbid.bid_any > 0 and n_sat > 0)
                    )
        else:
            return subtaskbid.N_req == n_sat
            

    def bundle_contains_mutex_subtasks(self, bundle : list, req : MeasurementRequest, subtask_index : int) -> bool:
        """
        Returns true if a bundle contains a subtask that is mutually exclusive to a subtask being added

        ### Arguments:
            - bundle (`list`) : current bundle to be expanded
            - req (:obj:`MeasurementRequest`) : request to be added to the bundle
            - subtask_index (`int`) : index of the subtask to be added to the bundle
        """
        for req_i, subtask_index_i in bundle:
            req_i : MeasurementRequest
            subtask_index_i : int 

            if req_i.id != req.id:
                # subtasks reffer to different tasks, cannot be mutually exclusive
                continue

            if (
                    req_i.dependency_matrix[subtask_index_i][subtask_index] < 0
                or  req_i.dependency_matrix[subtask_index][subtask_index_i] < 0
                ):
                # either the existing subtask in the bundle is mutually exclusive with the subtask to be added or viceversa
                return True
            
        return False

    def request_has_been_performed(self, results : dict, req : MeasurementRequest, subtask_index : int, t : Union[int, float]) -> bool:
        current_bid : SubtaskBid = results[req.id][subtask_index]
        subtask_already_performed = t > current_bid.t_img and current_bid.winner != SubtaskBid.NONE
        if subtask_already_performed:
            return True

        for subtask_bid in results[req.id]:
            subtask_bid : SubtaskBid
            
            if t > subtask_bid.t_img and subtask_bid.winner != SubtaskBid.NONE:
                return True
        
        return False

    def calc_path_bid(
                        self, 
                        state : SimulationAgentState, 
                        original_results : dict,
                        original_path : list, 
                        req : MeasurementRequest, 
                        subtask_index : int
                    ) -> tuple:
        state : SimulationAgentState = state.copy()
        winning_path = None
        winning_bids = None
        winning_path_utility = 0.0

        # check if the subtask is mutually exclusive with something in the bundle
        for req_i, subtask_j in original_path:
            req_i : MeasurementRequest; subtask_j : int
            if req_i.id == req.id:
                if req.dependency_matrix[subtask_j][subtask_index] < 0:
                    return winning_path, winning_bids, winning_path_utility

        # find best placement in path
        # self.log_task_sequence('original path', original_path, level=logging.WARNING)
        for i in range(len(original_path)+1):
            # generate possible path
            path = [scheduled_task for scheduled_task in original_path]
            
            path.insert(i, (req, subtask_index))
            # self.log_task_sequence('new proposed path', path, level=logging.WARNING)

            # calculate bids for each task in the path
            bids = {}
            for req_i, subtask_j in path:
                # predict state
                if i == 0:
                    t_prev = state.t
                    prev_state = state
                else:
                    prev_req, prev_subtask_index = path[i-1]
                    prev_req : MeasurementRequest; prev_subtask_index : int
                    bid_prev : Bid = bids[prev_req.id][prev_subtask_index]
                    t_prev : float = bid_prev.t_img + prev_req.duration

                    if isinstance(state, SatelliteAgentState):
                        prev_state : SatelliteAgentState = state.propagate(t_prev)
                        
                        prev_state.attitude = [
                                                prev_state.calc_off_nadir_agle(prev_req),
                                                0.0,
                                                0.0
                                            ]
                    else:
                        raise NotImplementedError(f"cannot calculate imaging time for agent states of type {type(state)}")

                # calculate imaging time
                req_i : MeasurementRequest
                subtask_j : int
                t_img = self.calc_imaging_time(prev_state, original_results, req_i, subtask_j, t_prev)

                if isinstance(prev_state, SatelliteAgentState):
                    future_state : SatelliteAgentState = prev_state.propagate(t_prev)
                    future_state.attitude = [
                                            future_state.calc_off_nadir_agle(req_i),
                                            0.0,
                                            0.0
                                        ]
                else:
                    raise NotImplementedError(f"cannot calculate future state for agent states of type {type(state)}")


                # calculate bidding score
                params = {"prev_state" : future_state, "req" : req_i, "subtask_index" : subtask_j, "t_img" : t_img}
                utility = self.utility_func(**params) if req_i.t_start <= t_img < req_i.t_end else 0.0

                # create bid
                bid : SubtaskBid = original_results[req_i.id][subtask_j].copy()
                bid.set_bid(utility, t_img, state.t)
                
                if req_i.id not in bids:
                    bids[req_i.id] = {}    
                bids[req_i.id][subtask_j] = bid                

            # look for path with the best utility
            path_utility = self.sum_path_utility(path, bids)
            if path_utility > winning_path_utility:
                winning_path = path
                winning_bids = bids
                winning_path_utility = path_utility

        return winning_path, winning_bids, winning_path_utility

    def calc_imaging_time(self, prev_state : SimulationAgentState, current_results : dict, req : MeasurementRequest, subtask_index : int, t_prev : float) -> float:
        """
        Computes the earliest time when a task in the path would be performed

        ### Arguments:

        ### Returns
            - t_imgs (`list`): list of available imaging times
        """
        # compute earliest time to the task
        t_imgs : list = self.calc_arrival_times(prev_state, req, t_prev)
        t_imgs = sorted(t_imgs)
        
        # get active time constraints
        t_consts = []
        for subtask_index_dep in range(len(current_results[req.id])):
            dep_bid : SubtaskBid = current_results[req.id][subtask_index_dep]
            
            if dep_bid.winner == SubtaskBid.NONE:
                continue

            if req.dependency_matrix[subtask_index][subtask_index_dep] > 0:
                t_corr = req.time_dependency_matrix[subtask_index][subtask_index_dep]
                t_consts.append((dep_bid.t_img, t_corr))
        
        if len(t_consts) > 0:
            # sort time-constraints in ascending order
            t_consts = sorted(t_consts)
            
            # choose an imaging time satisfies the latest time constraints
            t_const, t_corr = t_consts.pop()
            
            for t_img in t_imgs:
                if t_img + t_corr < t_const:
                    # i am performing my measurement before the other agent's earliest time; meet its imaging time
                    # t_img = t_const - t_corr
                    continue
                else:
                    # other agent images before my earliest time; expect other bidder to met my schedule
                    # or `t_img` satisfies this time constraint; no action required
                    return t_img
        
        elif len(t_imgs) > 0:
            return t_imgs[0]

        return np.Inf

    def calc_arrival_times(self, state : SimulationAgentState, req : MeasurementRequest, t_prev : Union[int, float]) -> float:
        """
        Estimates the quickest arrival time from a starting position to a given final position
        """
        t_imgs = []
        if isinstance(req, GroundPointMeasurementRequest):
            # compute earliest time to the task
            if self.parent_agent_type == SimulationAgentTypes.SATELLITE.value:
                lat,lon,_ = req.lat_lon_pos
                df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, t_prev)

                for _, row in df.iterrows():
                    t_img = row['time index'] * self.orbitdata.time_step
                    dt = t_img - state.t

                    # check for planning horizon
                    # if dt > self.planning_horizon:
                    #     continue
                                        
                    # propagate state
                    propagated_state : SatelliteAgentState = state.propagate(t_img)

                    # compute off-nadir angle
                    thf = propagated_state.calc_off_nadir_agle(req)
                    dth = thf - propagated_state.attitude[0]

                    # estimate arrival time using fixed angular rate TODO change to 
                    if dt >= abs(dth / 1.0): # TODO change maximum angular rate 
                        t_imgs.append(t_img)

                return t_imgs
            else:
                raise NotImplementedError(f"arrival time estimation for agents of type {self.parent_agent_type} is not yet supported.")

        else:
            raise NotImplementedError(f"cannot calculate imaging time for measurement requests of type {type(req)}")   

    def sum_path_utility(self, path : list, bids : dict) -> float:
        utility = 0.0
        for req, subtask_index in path:
            req : MeasurementRequest
            bid : SubtaskBid = bids[req.id][subtask_index]
            utility += bid.own_bid

        return utility

    def coalition_test(self, current_results : dict, proposed_bid : SubtaskBid) -> float:
        """
        This minimality in the size of coalitions is enforced during the two
        phases of the Modified CCBBA algorithm. In the first phase, it is carried
        out via the COALITIONTEST subroutine (see Algorithm 1, line 14).
        This elimination of waste of resources works by facilitating winning
        a particular subtask j if the bidding agent has previously won all other
        dependent subtasks. Specifically, the bid placed for each subtask, cj
        a, is compared to the sum of the bids of the subtasks that share a dependency
        constraint with j (D(j, q) = 1) rather than the bid placed on the
        single subtask j. This is implemented through an availability indicator hj

        ### Arguments:
            - current_results (`dict`): list of current bids
            - proposed_bid (:obj:`SubtaskBid`): proposed bid to be added to the bundle
        """
        # initiate agent bid count
        agent_bid = proposed_bid.winning_bid

        # initiate coalition bid count
        current_bid : SubtaskBid = current_results[proposed_bid.req_id][proposed_bid.subtask_index]
        coalition_bid = 0

        for bid_i in current_results[proposed_bid.req_id]:
            bid_i : SubtaskBid
            bid_i_index = current_results[proposed_bid.req_id].index(bid_i)

            if (    bid_i.winner == current_bid.winner
                and current_bid.dependencies[bid_i_index] >= 0 ):
                coalition_bid += bid_i.winning_bid

            if (    bid_i.winner == proposed_bid.winner 
                 and proposed_bid.dependencies[bid_i_index] == 1):
                agent_bid += bid_i.winning_bid

        return agent_bid > coalition_bid
    
    def mutex_test(self, current_results : dict, proposed_bid : SubtaskBid) -> bool:
        # calculate total agent bid count
        agent_bid = proposed_bid.winning_bid
        agent_coalition = [proposed_bid.subtask_index]
        for bid_i in current_results[proposed_bid.req_id]:
            bid_i : SubtaskBid
            bid_i_index = current_results[proposed_bid.req_id].index(bid_i)

            if bid_i_index == proposed_bid.subtask_index:
                continue

            if proposed_bid.dependencies[bid_i_index] == 1:
                agent_bid += bid_i.winning_bid
                agent_coalition.append(bid_i_index)

        # initiate coalition bid count
        ## find all possible coalitions
        task = MeasurementRequest.from_dict(proposed_bid.req)
        possible_coalitions = []
        for i in range(len(task.dependency_matrix)):
            coalition = [i]
            for j in range(len(task.dependency_matrix[i])):
                if task.dependency_matrix[i][j] == 1:
                    coalition.append(j)
            possible_coalitions.append(coalition)
        
        # calculate total mutex bid count
        max_mutex_bid = 0
        for coalition in possible_coalitions:
            mutex_bid = 0
            for coalition_member in coalition:
                bid_i : SubtaskBid = current_results[proposed_bid.req_id][coalition_member]

                if proposed_bid.subtask_index == coalition_member:
                    continue
                
                is_mutex = True
                for agent_coalition_member in agent_coalition:
                  if task.dependency_matrix[coalition_member][agent_coalition_member] >= 0:
                    is_mutex = False  
                    break

                if not is_mutex:
                    break
                
                mutex_bid += bid_i.winning_bid

            max_mutex_bid = max(mutex_bid, max_mutex_bid)

        return agent_bid > max_mutex_bid

    def path_constraint_sat(self, path : list, results : dict, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids of every task in the current path have all of their constraints
        satisfied by other bids.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        for req, subtask_index in path:
            # check constraints
            req : MeasurementRequest
            if not self.check_task_constraints(results, req, subtask_index, t_curr):
                return False
            
            # check local convergence
            my_bid : SubtaskBid = results[req.id][subtask_index]
            if t_curr < my_bid.t_update + my_bid.dt_converge:
                return False

        return True

    def check_task_constraints(self, results : dict, req : MeasurementRequest, subtask_index : int, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids in the current results satisfy the constraints of a given task.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        bid : SubtaskBid = results[req.id][subtask_index]
        bid_copy : SubtaskBid = bid.copy()
        constraint_sat, _ = bid_copy.check_constraints(results[req.id], t_curr)
        return constraint_sat is None

    def plan_from_path( self, 
                        state : SimulationAgentState, 
                        results : dict, 
                        path : list
                    ) -> list:
        """
        Generates a list of AgentActions from the current path.

        Agents look to move to their designated measurement target and perform the measurement.
        """

        plan = []
        for i in range(len(path)):
            measurement_req, subtask_index = path[i]
            measurement_req : MeasurementRequest; subtask_index : int
            subtask_bid : SubtaskBid = results[measurement_req.id][subtask_index]

            if not isinstance(measurement_req, GroundPointMeasurementRequest):
                raise NotImplementedError(f"Cannot create plan for requests of type {type(measurement_req)}")
            
            if i == 0:
                t_prev = state.t
                prev_state = state
            else:
                prev_req, prev_subtask_index = path[i-1]
                prev_req : MeasurementRequest; prev_subtask_index : int
                bid_prev : Bid = results[prev_req.id][prev_subtask_index]
                t_prev : float = bid_prev.t_img + prev_req.duration

                if isinstance(state, SatelliteAgentState):
                    prev_state : SatelliteAgentState = state.propagate(t_prev)
                    prev_state.attitude = [
                                        prev_state.calc_off_nadir_agle(prev_req),
                                        0.0,
                                        0.0
                                    ]
                else:
                    raise NotImplementedError(f"cannot calculate travel time start for agent states of type {type(state)}")

            # point to target
            if isinstance(state, SatelliteAgentState):
                t_maneuver_start = prev_state.t
                tf = prev_state.calc_off_nadir_agle(measurement_req)
                t_maneuver_end = t_maneuver_start + abs(tf - prev_state.attitude[0]) / 1.0 # TODO change max attitude rate 
            else:
                raise NotImplementedError(f"cannot calculate maneuver time end for agent states of type {type(state)}")
            if t_maneuver_start == -1.0:
                continue
            if abs(t_maneuver_start - t_maneuver_end) >= 1e-3:
                maneuver_action = ManeuverAction([tf, 0, 0], t_maneuver_start, t_maneuver_end)
                plan.append(maneuver_action)

            # move to target
            t_move_start = t_maneuver_end
            if isinstance(state, SatelliteAgentState):
                lat, lon, _ = measurement_req.lat_lon_pos
                df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, t_move_start)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    t_move_end = row['time index'] * self.orbitdata.time_step
                    break

                future_state : SatelliteAgentState = state.propagate(t_move_end)
                final_pos = future_state.pos
            else:
                raise NotImplementedError(f"cannot calculate travel time end for agent states of type {type(state)}")
            
            t_img_start = t_move_end
            t_img_end = t_img_start + measurement_req.duration

            if isinstance(self._clock_config, FixedTimesStepClockConfig):
                dt = self._clock_config.dt
                if t_move_start < np.Inf:
                    t_move_start = dt * math.floor(t_move_start/dt)
                if t_move_end < np.Inf:
                    t_move_end = dt * math.ceil(t_move_end/dt)

                if t_img_start < np.Inf:
                    t_img_start = dt * math.ceil(t_img_start/dt)
                if t_img_end < np.Inf:
                    t_img_end = dt * math.ceil((t_img_start + measurement_req.duration)/dt)
            
            if abs(t_move_start - t_move_end) >= 1e-3:
                move_action = TravelAction(final_pos, t_move_start, t_move_end)
                plan.append(move_action)
            
            # perform measurement
            measurement_action = MeasurementAction( 
                                                    measurement_req.to_dict(),
                                                    subtask_index, 
                                                    subtask_bid.main_measurement,
                                                    subtask_bid.winning_bid,
                                                    t_img_start, 
                                                    t_img_end
                                                    )
            plan.append(measurement_action)  
        
        return plan

    
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
    def log_results(self, dsc : str, results : dict, level=logging.DEBUG) -> None:
        """
        Logs current results at a given time for debugging purposes

        ### Argumnents:
            - dsc (`str`): description of what is to be logged
            - results (`dict`): results to be logged
            - level (`int`): logging level to be used
        """
        if self._logger.getEffectiveLevel() <= level:
            headers = ['task_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for task_id in results:
                if isinstance(results[task_id], list):
                    for bid in results[task_id]:
                        bid : SubtaskBid
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                elif isinstance(results[task_id], dict):
                    for bid_index in results[task_id]:
                        bid : SubtaskBid = results[task_id][bid_index]
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                else:
                    raise ValueError(f'`results` must be of type `list` or `dict`. is of type {type(results)}')

            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)
    
    def log_task_sequence(self, dsc : str, sequence : list, level=logging.DEBUG) -> None:
        """
        Logs a sequence of tasks at a given time for debugging purposes

        ### Argumnents:
            - dsc (`str`): description of what is to be logged
            - sequence (`list`): list of tasks to be logged
            - level (`int`): logging level to be used
        """
        if self._logger.getEffectiveLevel() <= level:
            out = f'\n{dsc} [Iter {self.iter_counter}] = ['
            for req, subtask_index in sequence:
                req : MeasurementRequest
                subtask_index : int
                split_id = req.id.split('-')
                
                if sequence.index((req, subtask_index)) > 0:
                    out += ', '
                out += f'({split_id[0]}, {subtask_index})'
            out += ']\n'

            self.log(out,level)

    def log_changes(self, dsc : str, changes : list, level=logging.DEBUG) -> None:
        if self._logger.getEffectiveLevel() <= level:
            headers = ['task_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for change in changes:
                change : MeasurementBidMessage
                bid = SubtaskBid(**change.bid)
                req = MeasurementRequest.from_dict(bid.req)
                split_id = req.id.split('-')
                line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                data.append(line)
        
            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

    def log_plan(self, results : dict, plan : list, t : Union[int, float], level=logging.DEBUG) -> None:
        headers = ['t', 'task_id', 'subtask_index', 't_start', 't_end', 't_img', 'u_exp']
        data = []

        for action in plan:
            if isinstance(action, MeasurementAction):
                req : MeasurementRequest = MeasurementRequest.from_dict(action.measurement_req)
                task_id = req.id.split('-')[0]
                subtask_index : int = action.subtask_index
                subtask_bid : SubtaskBid = results[req.id][subtask_index]
                t_img = subtask_bid.t_img
                winning_bid = subtask_bid.winning_bid
            elif isinstance(action, TravelAction) or isinstance(action, ManeuverAction):
                task_id = action.id.split('-')[0]
                subtask_index = -1
                t_img = -1
                winning_bid = -1
            else:
                continue
            
            line_data = [   t,
                            task_id,
                            subtask_index,
                            np.round(action.t_start,3 ),
                            np.round(action.t_end,3 ),
                            np.round(t_img,3 ),
                            np.round(winning_bid,3)
            ]
            data.append(line_data)

        df = pd.DataFrame(data, columns=headers)
        self.log(f'\nPLANNER HISTORY\n{str(df)}\n', level)

    async def teardown(self) -> None:
        # log plan history
        headers = ['plan_index', 't', 'task_id', 'subtask_index', 't_img', 'u_exp']
        data = []

        for i in range(len(self.plan_history)):
            for t, req, subtask_index, subtask_bid in self.plan_history[i]:
                req : MeasurementRequest
                subtask_index : int
                subtask_bid : SubtaskBid
                
                line_data = [   i,
                                t,
                                req.id.split('-')[0],
                                subtask_index,
                                np.round(subtask_bid.t_img,3 ),
                                np.round(subtask_bid.winning_bid,3)
                ]
                data.append(line_data)

        df = pd.DataFrame(data, columns=headers)
        self.log(f'\nPLANNER HISTORY\n{str(df)}\n', level=logging.WARNING)
        df.to_csv(f"{self.results_path}/{self.get_parent_name()}/planner_history.csv", index=False)

        await super().teardown()