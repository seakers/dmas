import asyncio
from ctypes import Union
import logging
import math
import time
from typing import Any, Callable
import zmq
import numpy as np
import pandas as pd

from nodes.orbitdata import OrbitData
from nodes.states import *
from nodes.actions import *
from nodes.states import SimulationAgentState
from nodes.science.utility import synergy_factor
from nodes.science.reqs import MeasurementRequest
from nodes.planning.planners import Bid, PlanningModule
from nodes.planning.mccbba import *
from messages import *

from dmas.messages import *
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
                    t_violation: Union[float, int] = np.Inf, 
                    dt_violoation: Union[float, int] = 1e-6,
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
                return self, prev!=self
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
                return other, prev!=self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                self._leave(t)
                return None, False

        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev!=self

                if other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return self, prev!=self

            elif self.winner == other.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

                elif other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.t_update < self.t_update:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

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
                    return other, prev!=self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self

        elif other.winner == self.bidder:
            if self.winner == self.NONE:
                # leave and rebroadcast with current update time
                self.__update_time(t)
                return self, prev!=self

            elif self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False
                
            elif self.winner == other.bidder and other.bidder != self.bidder:
                # reset and rebroadcast with current update time
                self.reset(t)
                return self, prev!=self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                # leave and rebroadcast
                self._leave(t)
                return self, False

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev!=self

                elif other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return other, prev!=self

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self

            elif self.winner == other.winner:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
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
                    return other, prev!=self

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False
                    
                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, prev!=self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self
        
        return None, prev!=self

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
        self.t_violation = t_update if 1 in self.time_constraints else np.Inf
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
        # if self.winner == self.bidder:
        #     self.t_violation = -1
        self.t_violation = np.Inf
        return

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

class BidBuffer(object):
    """
    Asynchronous buffer that holds bid information for use by processes within the MACCBBA
    """
    
    def __init__(self) -> None:
        self.bid_access_lock = asyncio.Lock()
        self.bid_buffer = {}
        self.updated = asyncio.Event()             

    def __len__(self) -> int:
        l = 0
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : SubtaskBid
                l += 1 if bid is not None else 0
        return l

    async def pop_all(self) -> list:
        """
        Returns latest bids for all requests and empties buffer
        """
        await self.bid_access_lock.acquire()

        out = []
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : SubtaskBid
                if bid is not None:
                    # place bid in outgoing list
                    out.append(bid.copy())

            # reset bids in buffer
            self.bid_buffer[req_id] = [None for _ in self.bid_buffer[req_id]]

        self.bid_access_lock.release()

        return out

    async def put_bid(self, new_bid : SubtaskBid) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        await self.bid_access_lock.acquire()

        if new_bid.req_id not in self.bid_buffer:
            req : MeasurementRequest = MeasurementRequest.from_dict(new_bid.req)
            self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

        current_bid : SubtaskBid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]

        if current_bid is None or new_bid.t_update >= current_bid.t_update:
            self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()

        self.bid_access_lock.release()

        self.updated.set()
        self.updated.clear()

    async def put_bids(self, new_bids : list) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        if len(new_bids) == 0:
            return

        await self.bid_access_lock.acquire()

        for new_bid in new_bids:
            new_bid : SubtaskBid

            if new_bid.req_id not in self.bid_buffer:
                req : MeasurementRequest = MeasurementRequest.from_dict(new_bid.req)
                self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

            current_bid : SubtaskBid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]

            if current_bid is None or new_bid.t_update >= current_bid.t_update:
                self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()

        self.bid_access_lock.release()

        self.updated.set()
        self.updated.clear()

    async def wait_for_updates(self, min_len : int = 1) -> list:
        """
        Waits for the contents of this buffer to be updated and to contain more updates than the given minimum
        """
        while True:
            await self.updated.wait()

            if len(self) >= min_len:
                break

        return await self.pop_all()


class MACCBBA(PlanningModule):
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
    
    async def setup(self) -> None:
        await super().setup()

        self.listener_to_builder_buffer = BidBuffer()
        self.listener_to_broadcaster_buffer = BidBuffer()
        self.builder_to_broadcaster_buffer = BidBuffer()
        self.broadcasted_bids_buffer = BidBuffer()

        self.t_curr = 0
        self.agent_state : SimulationAgentState = None
        self.agent_state_lock = asyncio.Lock()
        self.agent_state_updated = asyncio.Event()
        self.parent_agent_type = None
        self.orbitdata = None
        self.plan_inbox = asyncio.Queue()

    async def live(self) -> None:
        """
        Performs three concurrent tasks:
        - Listener: receives messages from the parent agent and updates internal results
        - Bundle-builder: plans and bids according to local information
        - Planner: listens for requests from parent agent and returns latest plan to perform
        """
        try:
            listener_task = asyncio.create_task(self.listener(), name='listener()')
            bundle_builder_task = asyncio.create_task(self.bundle_builder(), name='bundle_builder()')
            planner_task = asyncio.create_task(self.planner(), name='planner()')
            
            tasks = [listener_task, bundle_builder_task, planner_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        finally:
            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                if not task.done():
                    task.cancel()
                    await task

    async def listener(self) -> None:
        """
        Listens for any incoming messages, unpacks them and classifies them into 
        internal inboxes for future processing
        """
        try:
            # initiate results tracker
            results = {}
            # level = logging.WARNING
            level = logging.DEBUG

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                    return

                elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!", level=logging.DEBUG)

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)  

                    incoming_bids = []   
                    state : SimulationAgentState = None

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                            # unpack message 
                            action_msg = AgentActionMessage(**sense)
                            self.log(f"received agent action of status {action_msg.status}!")
                            
                            # send to planner
                            await self.action_status_inbox.put(action_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                            # unpack message 
                            state_msg : AgentStateMessage = AgentStateMessage(**sense)
                            self.log(f"received agent state message!")
                                                        
                            # update current state
                            await self.agent_state_lock.acquire()
                            state : SimulationAgentState = SimulationAgentState.from_dict(state_msg.state)

                            await self.update_current_time(state.t)
                            self.agent_state = state

                            if self.parent_agent_type is None:
                                if isinstance(state, SatelliteAgentState):
                                    # import orbit data
                                    self.orbitdata : OrbitData = self._load_orbit_data()
                                    self.parent_agent_type = SimulationAgentTypes.SATELLITE.value
                                elif isinstance(state, UAVAgentState):
                                    self.parent_agent_type = SimulationAgentTypes.UAV.value
                                else:
                                    raise NotImplementedError(f"states of type {state_msg.state['state_type']} not supported for greedy planners.")
                            
                            self.agent_state_lock.release()

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_REQ.value:
                            # unpack message 
                            req_msg = MeasurementRequestMessage(**sense)
                            req = MeasurementRequest.from_dict(req_msg.req)
                            self.log(f"received measurement request message!")
                            
                            # if not in send to planner
                            if req.id not in results:
                                # create task bid from measurement request and add to results
                                self.log(f"received new measurement request! Adding to results ledger...")

                                bids : list = SubtaskBid.subtask_bids_from_task(req, self.get_parent_name())
                                # results[req.id] = bids
                                incoming_bids.extend(bids)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            bid : SubtaskBid = SubtaskBid(**bid_msg.bid)
                            self.log(f"received measurement request message!")
                            
                            incoming_bids.append(bid)

                    if len(self.broadcasted_bids_buffer) > 0:
                        broadcasted_bids : list = await self.broadcasted_bids_buffer.pop_all()
                        incoming_bids.extend(broadcasted_bids)                    
                    
                    if len(incoming_bids) > 0:
                        results, bundle, path, \
                        consensus_changes, rebroadcast_bids = self.consensus_phase( results, 
                                                                                    [], 
                                                                                    [], 
                                                                                    self.get_current_time(),
                                                                                    incoming_bids,
                                                                                    level
                                                                                )
                        sorting_buffer = BidBuffer()
                        await sorting_buffer.put_bids(rebroadcast_bids)
                        rebroadcast_bids = await sorting_buffer.pop_all()

                        self.log_changes("listener - CHANGES MADE FROM CONSENSUS", consensus_changes, level)
                        self.log_changes("listener - REBROADCASTS TO BE DONE", rebroadcast_bids, level)

                        # send to bundle-builder and broadcaster
                        await self.listener_to_builder_buffer.put_bids(rebroadcast_bids)
                        await self.listener_to_broadcaster_buffer.put_bids(rebroadcast_bids)

                    # inform planner of state update
                    self.agent_state_updated.set()
                    self.agent_state_updated.clear()
                    
                    await self.states_inbox.put(state) 

        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results

    async def bundle_builder(self) -> None:
        try:
            results = {}
            path = []
            bundle = []
            # level = logging.WARNING
            level = logging.DEBUG

            while True:
                # wait for incoming bids
                incoming_bids = await self.listener_to_builder_buffer.wait_for_updates()
                self.log_changes('BIDS RECEIVED', incoming_bids, level)

                # Consensus Phase 
                t_0 = time.perf_counter()
                results, bundle, path, consensus_changes, \
                consensus_rebroadcasts = self.consensus_phase(  results, 
                                                                bundle, 
                                                                path, 
                                                                self.get_current_time(),
                                                                incoming_bids,
                                                                level
                                                            )
                dt = time.perf_counter() - t_0
                self.stats['consensus'].append(dt)

                self.log_changes("builder - CHANGES MADE FROM CONSENSUS", consensus_changes, level)

                # Update iteration counter
                self.iter_counter += 1

                # Planning Phase
                t_0 = time.perf_counter()
                results, bundle, path,\
                     planner_changes = self.planning_phase( self.agent_state, 
                                                            results, 
                                                            bundle, 
                                                            path, 
                                                            level
                                                        )
                dt = time.perf_counter() - t_0
                self.stats['planning'].append(dt)

                broadcast_buffer = BidBuffer()
                await broadcast_buffer.put_bids(planner_changes)
                planner_changes = await broadcast_buffer.pop_all()
                self.log_changes("builder - CHANGES MADE FROM PLANNING", planner_changes, level)
                
                # Check for convergence
                converged = self.path_constraint_sat(path, results, self.get_current_time())
                if converged:
                    converged = self.path_constraint_sat(path, results, self.get_current_time())
                    
                    # generate plan from path
                    await self.agent_state_lock.acquire()
                    plan = self.plan_from_path(self.agent_state, results, path)
                    self.agent_state_lock.release()

                else:
                    # wait for messages or for next bid time-out
                    t_next = np.Inf
                    for req, subtask_index in path:
                        req : MeasurementRequest
                        bid : SubtaskBid = results[req.id][subtask_index]

                        if bid.winner == SubtaskBid.NONE:
                            continue

                        t_timeout = bid.t_violation + bid.dt_violation
                        if t_timeout < t_next:
                            t_next = t_timeout

                    wait_action = WaitForMessages(self.get_current_time(), t_next)
                    plan = [wait_action]
                
                # Broadcast changes to bundle and any changes from consensus
                broadcast_bids : list = consensus_rebroadcasts
                broadcast_bids.extend(planner_changes)
                
                broadcast_buffer = BidBuffer()
                await broadcast_buffer.put_bids(broadcast_bids)
                broadcast_bids = await broadcast_buffer.pop_all()
                self.log_changes("builder - REBROADCASTS TO BE DONE", broadcast_bids, level)
                await self.builder_to_broadcaster_buffer.put_bids(broadcast_bids)                                

                # Send plan to broadcaster
                await self.plan_inbox.put(plan)

        except asyncio.CancelledError:
            return
        finally:
            self.bundle_builder_results = results 

    async def planner(self) -> None:
        try:
            self.plan = []
            # level = logging.WARNING
            level = logging.DEBUG

            while True:
                # wait for agent to update state
                _ : AgentStateMessage = await self.states_inbox.get()

                # --- Look for Plan Updates ---

                plan_out = []
                # Check if relevant changes to the bundle were performed
                if len(self.listener_to_broadcaster_buffer) > 0:
                    # wait for plan to be updated
                    self.plan : list = await self.plan_inbox.get()

                    # compule updated bids from the listener and bundle buiilder
                    if len(self.builder_to_broadcaster_buffer) > 0:
                        # received bids to rebroadcast from bundle-builder
                        bids : list = await self.builder_to_broadcaster_buffer.pop_all()
                        
                        # communicate updates to listener
                        await self.broadcasted_bids_buffer.put_bids(bids)
                        
                        # received bids to rebroadcast from listener    
                        bids.extend(await self.listener_to_broadcaster_buffer.pop_all())

                        # add bid broadcasts to plan
                        rebroadcast_bids = self.compile_bids(bids)
                        for req_id in rebroadcast_bids:
                            for bid in rebroadcast_bids[req_id]:
                                bid : SubtaskBid
                                if bid is not None:
                                    bid_message = MeasurementBidMessage(self.get_parent_name(), self.get_parent_name(), bid.to_dict())
                                    plan_out.append( BroadcastMessageAction(bid_message.to_dict(), self.get_current_time()).to_dict() )
                    else:
                        # flush redundant broadcasts from listener
                        _ = await self.listener_to_broadcaster_buffer.pop_all()

                # --- Execute plan ---

                # check plan completion 
                while not self.action_status_inbox.empty():
                    action_msg : AgentActionMessage = await self.action_status_inbox.get()
                    action : AgentAction = action_from_dict(**action_msg.action)

                    if action_msg.status == AgentAction.PENDING:
                        # if action wasn't completed, try again
                        plan_ids = [action.id for action in self.plan]
                        action_dict : dict = action_msg.action
                        if action_dict['id'] in plan_ids:
                            self.log(f'action {action_dict} not completed yet! trying again...')
                            plan_out.append(action_dict)

                    else:
                        # if action was completed or aborted, remove from plan
                        action_dict : dict = action_msg.action
                        completed_action = AgentAction(**action_dict)
                        removed = None
                        for action in self.plan:
                            action : AgentAction
                            if action.id == completed_action.id:
                                removed = action
                                break
                        
                        if removed is not None:
                            removed : AgentAction
                            self.plan : list
                            self.plan.remove(removed)
                            removed = removed.to_dict()

                # get next action to perform
                if len(plan_out) == 0:
                    plan_out_ids = [action['id'] for action in plan_out]
                    for action in self.plan:
                        action : AgentAction
                        if (action.t_start <= self.get_current_time()
                            and action.id not in plan_out_ids):
                            plan_out.append(action.to_dict())

                    if len(plan_out) == 0:
                        if len(self.plan) > 0:
                            # next action is yet to start, wait until then
                            next_action : AgentAction = self.plan[0]
                            t_idle = next_action.t_start if next_action.t_start > self.get_current_time() else self.get_current_time()
                        else:
                            # no more actions to perform, idle until the end of the simulation
                            t_idle = np.Inf

                        action = WaitForMessages(self.get_current_time(), t_idle)
                        plan_out.append(action.to_dict())

                # --- FOR DEBUGGING PURPOSES ONLY: ---
                out = f'\nPLAN\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end\n'
                for action in self.plan:
                    action : AgentAction
                    out += f"{action.id.split('-')[0]}, {action.action_type}, {action.t_start}, {action.t_end}\n"
                self.log(out, level)

                out = f'\nPLAN OUT\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end\n'
                for action in plan_out:
                    action : dict
                    out += f"{action['id'].split('-')[0]}, {action['action_type']}, {action['t_start']}, {action['t_end']}\n"
                self.log(out, level)
                # -------------------------------------

                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

    """
    -----------------------
        CONSENSUS PHASE
    -----------------------
    """
    def consensus_phase(  
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
        results, bundle, path, \
            comp_changes, comp_rebroadcasts = self.compare_results(results, bundle, path, t, new_bids, level)
        changes.extend(comp_changes)
        rebroadcasts.extend(comp_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_comp_check'].append(dt)

        self.log_changes('BIDS RECEIVED', new_bids, level)
        self.log_results('COMPARED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)
        
        # check for expired tasks
        t_0 = time.perf_counter()
        results, bundle, path, \
            exp_changes, exp_rebroadcasts = self.check_request_end_time(results, bundle, path, t, level)
        changes.extend(exp_changes)
        rebroadcasts.extend(exp_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check for already performed tasks
        t_0 = time.perf_counter()
        results, bundle, path, \
            done_changes, done_rebroadcasts = self.check_request_completion(results, bundle, path, t, level)
        changes.extend(done_changes)
        rebroadcasts.extend(done_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check task constraint satisfaction
        t_0 = time.perf_counter()
        results, bundle, path, \
            cons_changes, cons_rebroadcasts = self.check_bid_constraints(results, bundle, path, t, level)
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

            req = MeasurementRequest.from_dict(their_bid.req)
            if new_req:
                # was not aware of this request; add to results as a blank bid
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

    def check_request_end_time(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
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

    def check_request_completion(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
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

    def check_bid_constraints(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.WARNING) -> tuple:
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

    def compile_bids(self, bids : list) -> dict:
        rebroadcast_bids = {}

        for bid in bids:
            bid : SubtaskBid
            
            if bid.req_id not in rebroadcast_bids:
                req = MeasurementRequest.from_dict(bid.req)
                rebroadcast_bids[bid.req_id] = [None for _ in req.dependency_matrix]
            
            current_bid : SubtaskBid = rebroadcast_bids[bid.req_id][bid.subtask_index]
            if (current_bid is None or current_bid.t_update <= bid.t_update):
                rebroadcast_bids[bid.req_id][bid.subtask_index] = bid

        return rebroadcast_bids

    """
    ----------------------
        PLANNING PHASE 
    ----------------------
    """
    def planning_phase(self, state : SimulationAgentState, results : dict, bundle : list, path : list, level : int = logging.DEBUG) -> None:
        """
        Uses the most updated results information to construct a path
        """
        self.log_results('INITIAL BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

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

        # max_utility = 0.0
        max_task = -1
        max_path_utility = self.sum_path_utility(max_path, max_path_bids)
        available_tasks : list = self.get_available_tasks(state, bundle, results)

        while len(bundle) < self.max_bundle_size and len(available_tasks) > 0 and max_task is not None:                   
            # find next best task to put in bundle (greedy)
            max_task = None 
            max_subtask = None
            for measurement_req, subtask_index in available_tasks:
                # calculate bid for a given available task
                measurement_req : MeasurementRequest
                subtask_index : int

                projected_path, projected_bids, projected_path_utility = self.calc_path_bid(state, results, path, measurement_req, subtask_index)
                
                # check if path was found
                if projected_path is None:
                    continue
                
                # compare to maximum task
                projected_utility = projected_bids[measurement_req.id][subtask_index].winning_bid
                current_utility = results[measurement_req.id][subtask_index].winning_bid
                if (max_task is None 
                    or (projected_utility > current_utility and projected_path_utility > max_path_utility)
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
                    # max_utility = projected_bids[measurement_req.id][subtask_index].winning_bid

            if max_task is not None:
                # max bid found! place task with the best bid in the bundle and the path
                bundle.append((max_task, max_subtask))
                path = max_path

                # remove bid task from list of available tasks
                # available_tasks.remove((max_task, max_subtask))
            
            # update results
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

            available_tasks : list = self.get_available_tasks(state, bundle, results)

        # broadcast changes to bundle
        for measurement_req, subtask_index in changes_to_bundle:
            measurement_req : MeasurementRequest
            subtask_index : int

            new_bid = results[measurement_req.id][subtask_index]

            # add to changes broadcast 
            changes.append(new_bid)

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
        for req_id in results:
            for subtask_index in range(len(results[req_id])):
                subtaskbid : SubtaskBid = results[req_id][subtask_index]; 
                req = MeasurementRequest.from_dict(subtaskbid.req)

                is_biddable = self.can_bid(state, req, subtask_index, results[req_id]) 
                already_in_bundle = self.check_if_in_bundle(req, subtask_index, bundle)
                already_performed = self.task_has_been_performed(results, req, subtask_index, state.t)
                
                if is_biddable and not already_in_bundle and not already_performed:
                    available.append((req, subtaskbid.subtask_index))

        return available

    def check_if_in_bundle(self, req : MeasurementRequest, subtask_index : int, bundle : list) -> bool:
        for req_i, subtask_index_j in bundle:
            if req_i.id == req.id and subtask_index == subtask_index_j:
                return True
    
        return False

    def can_bid(self, state : SimulationAgentState, req : MeasurementRequest, subtask_index : int, subtaskbids : list) -> bool:
        """
        Checks if an agent has the ability to bid on a measurement task
        """
        # check planning horizon
        if state.t + self.planning_horizon < req.t_start:
            return False

        # check capabilities - TODO: Replace with knowledge graph
        subtaskbid : SubtaskBid = subtaskbids[subtask_index]
        if subtaskbid.main_measurement not in [instrument.name for instrument in self.payload]:
            return False 

        # check time constraints
        ## Constraint 1: task must be able to be performed during or after the current time
        if req.t_end < state.t:
            return False

        elif isinstance(req, GroundPointMeasurementRequest):
            if isinstance(state, SatelliteAgentState):
                # check if agent can see the request location
                lat,lon,_ = req.lat_lon_pos
                df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, state.t)
                can_access = False
                if not df.empty:                
                    times = df.get('time index')
                    for time in times:
                        time *= self.orbitdata.time_step 

                        if time < req.t_end:
                            # there exists an access time before the request's availability ends
                            can_access = True
                            break
                
                if not can_access:
                    return False
            # elif isinstance(state, SatelliteAgentState): # TODO chech UAV range 
            #     pass

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
            
    def task_has_been_performed(self, results : dict, req : MeasurementRequest, subtask_index : int, t : Union[int, float]) -> bool:
        
        # check if subtask at hand has been performed
        current_bid : SubtaskBid = results[req.id][subtask_index]
        subtask_already_performed = t > current_bid.t_img + req.duration and current_bid.winner != SubtaskBid.NONE
        if subtask_already_performed or current_bid.performed:
            return True

        # check if a mutually exclusive subtask has already been performed
        for subtask_bid in results[req.id]:
            subtask_bid : SubtaskBid         

            if (
                t > subtask_bid.t_img + req.duration 
                and subtask_bid.winner != SubtaskBid.NONE
                and req.dependency_matrix[subtask_index][subtask_bid.subtask_index] < 0
                ):
                return True
        
        return False

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
            path = [scheduled_obs for scheduled_obs in original_path]
            
            path.insert(i, (req, subtask_index))
            # self.log_task_sequence('new proposed path', path, level=logging.WARNING)

            # calculate bids for each task in the path
            bids = {}
            for req_i, subtask_j in path:
                # calculate imaging time
                req_i : MeasurementRequest
                subtask_j : int
                t_img = self.calc_imaging_time(state, original_results, path, bids, req_i, subtask_j)

                # calc utility
                params = {"req" : req_i, "subtask_index" : subtask_j, "t_img" : t_img}
                utility = self.utility_func(**params) if t_img >= 0 else 0.0
                utility *= synergy_factor(**params)

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

    def calc_imaging_time(self, state : SimulationAgentState, original_results : dict, path : list, bids : dict, req : MeasurementRequest, subtask_index : int) -> float:
        """
        Computes the earliest time when a task in the path would be performed

        ### Arguments:

        ### Returns
            - t_imgs (`list`): list of available imaging times
        """
        i = path.index((req, subtask_index))
        if i == 0:
            t_prev = state.t
            prev_state = state.copy()
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
            elif isinstance(state, UAVAgentState):
                prev_state = state.copy()
                prev_state.t = t_prev
                
                if isinstance(prev_req, GroundPointMeasurementRequest):
                    prev_state.pos = prev_req.pos
                else:
                    raise NotImplementedError
            else:
                raise NotImplementedError(f"cannot calculate imaging time for agent states of type {type(state)}")

        # compute earliest time to the task
        t_imgs : list = self.calc_arrival_times(prev_state, req, t_prev,)
        t_imgs = sorted(t_imgs)
        
        # get active time constraints
        t_consts = []
        for subtask_index_dep in range(len(original_results[req.id])):
            dep_bid : SubtaskBid = original_results[req.id][subtask_index_dep]
            
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

        # add convergence timer if needed
        t_conv_min = np.Inf
        for measurement_req, subtask_index in path:
            bid : SubtaskBid = results[measurement_req.id][subtask_index]
            t_conv = bid.t_update + bid.dt_converge
            if t_conv < t_conv_min:
                t_conv_min = t_conv

        if state.t < t_conv_min:
            plan.append( WaitForMessages(state.t, t_conv_min) )
        else:
            t_conv_min = state.t

        # add actions per measurement
        for i in range(len(path)):
            measurement_req, subtask_index = path[i]
            measurement_req : MeasurementRequest; subtask_index : int
            subtask_bid : SubtaskBid = results[measurement_req.id][subtask_index]

            if not isinstance(measurement_req, GroundPointMeasurementRequest):
                raise NotImplementedError(f"Cannot create plan for requests of type {type(measurement_req)}")
            
            if i == 0:
                if isinstance(state, SatelliteAgentState):
                    t_prev = state.t
                    prev_state : SatelliteAgentState = state.copy()

                elif isinstance(state, UAVAgentState):
                    t_prev = t_conv_min
                    prev_state : UAVAgentState = state.copy()

                else:
                    raise NotImplementedError(f"cannot calculate travel time start for agent states of type {type(state)}")
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

                elif isinstance(state, UAVAgentState):
                    prev_state : UAVAgentState = state.copy()
                    prev_state.t = t_prev

                    if isinstance(prev_req, GroundPointMeasurementRequest):
                        prev_state.pos = prev_req.pos
                    else:
                        raise NotImplementedError(f"cannot calculate travel time start for requests of type {type(prev_req)} for uav agents")

                else:
                    raise NotImplementedError(f"cannot calculate travel time start for agent states of type {type(state)}")

            # maneuver to point to target
            t_maneuver_end = None
            if isinstance(state, SatelliteAgentState):
                prev_state : SatelliteAgentState

                t_maneuver_start = prev_state.t
                tf = prev_state.calc_off_nadir_agle(measurement_req)
                t_maneuver_end = t_maneuver_start + abs(tf - prev_state.attitude[0]) / 1.0 # TODO change max attitude rate 

                if t_maneuver_start == -1.0:
                    continue
                if abs(t_maneuver_start - t_maneuver_end) >= 1e-3:
                    maneuver_action = ManeuverAction([tf, 0, 0], t_maneuver_start, t_maneuver_end)
                    plan.append(maneuver_action)            

            # move to target
            t_move_start = t_prev if t_maneuver_end is None else t_maneuver_end
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

            elif isinstance(state, UAVAgentState):
                final_pos = measurement_req.pos
                dr = np.array(final_pos) - np.array(prev_state.pos)
                norm = np.sqrt( dr.dot(dr) )
                
                t_move_end = t_move_start + norm / state.max_speed

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
                    t_img_start = dt * math.floor(t_img_start/dt)
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

    """
    --------------------
    LOGGING AND TEARDOWN
    --------------------
    """
    def log_results(self, dsc : str, results : dict, level=logging.DEBUG) -> None:
        """
        Logs current results at a given time for debugging purposes

        ### Argumnents:
            - dsc (`str`): description of what is to be logged
            - results (`dict`): results to be logged
            - level (`int`): logging level to be used
        """
        if self._logger.getEffectiveLevel() <= level:
            headers = ['req_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for req_id in results:
                if isinstance(results[req_id], list):
                    for bid in results[req_id]:
                        bid : SubtaskBid
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                elif isinstance(results[req_id], dict):
                    for bid_index in results[req_id]:
                        bid : SubtaskBid = results[req_id][bid_index]
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
            headers = ['req_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_update', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for bid in changes:
                bid : SubtaskBid
                req = MeasurementRequest.from_dict(bid.req)
                split_id = req.id.split('-')
                line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_update, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                data.append(line)
        
            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

    def log_plan(self, results : dict, plan : list, t : Union[int, float], level=logging.DEBUG) -> None:
        headers = ['t', 'req_id', 'subtask_index', 't_start', 't_end', 't_img', 'u_exp']
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
        headers = ['plan_index', 't', 'req_id', 'subtask_index', 't_img', 'u_exp']
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