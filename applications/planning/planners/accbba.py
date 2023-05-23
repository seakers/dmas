"""
*********************************************************************************
    ___   ________________  ____  ___       ____  __                           
   /   | / ____/ ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
  / /| |/ /   / /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
 / ___ / /___/ /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
/_/  |_\____/\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

import copy
from itertools import combinations, permutations
import logging
import math
import time
from typing import Union
import numpy as np
from pandas import DataFrame
from applications.planning.messages import Union
from applications.planning.planners.planners import Union
from applications.planning.actions import Union
from dmas.modules import Union

from actions import *
from messages import *

from planners.planners import *
from planners.acbba import ACBBAPlannerModule
from planners.acbba import TaskBid

from dmas.agents import AgentAction
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig

class SubtaskBid(TaskBid):
    """
    ## Subtask Bid for ACBBA 

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - task (`dict`): task being bid on
        - task_id (`str`): id of the task being bid on
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
        - N_req (`int`): number of required constraints
    """
    def __init__(
                    self, 
                    task: dict, 
                    subtask_index : int,
                    main_measurement : str,
                    dependencies : list,
                    time_constraints : list,
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = TaskBid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    dt_converge: Union[float, int] = 0.0, 
                    t_violation: Union[float, int] = -1, 
                    dt_violoation: Union[float, int] = 0.0,
                    bid_solo : int = 3,
                    bid_any : int = 3, 
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
        """
        super().__init__(task, bidder, winning_bid, own_bid, winner, t_img, t_update, dt_converge, **_)

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

        if not isinstance(bid_any, int):
            raise ValueError(f'`bid_solo` must be of type `int`. Is of type {type(bid_any)}')
        elif bid_any < 0:
            raise ValueError(f'`bid_solo` must be a positive `int`. Was given value of {bid_any}.')
        self.bid_any = bid_any

    def update(self, other_dict : dict, t : Union[float, int]) -> tuple:
        broadcast_out, changed = super().update(other_dict, t)
        broadcast_out : TaskBid; changed : bool

        if broadcast_out is not None:
            other = SubtaskBid(**other_dict)
            if other.bidder == broadcast_out.bidder:
                return other, changed
            else:
                return self, changed
        return None, changed

    def set_bid(self, new_bid : Union[int, float], t_img : Union[int, float], t_update : Union[int, float]) -> None:
        """
        Sets new values for this bid

        ### Arguments: 
            - new_bid (`int` or `float`): new bid value
            - t_img (`int` or `float`): new imaging time
            - t_update (`int` or `float`): update time
        """
        self.own_bid = new_bid
        # if new_bid < self.winning_bid:
        #     raise ValueError(f"`new_bid` can only be set with values higher than the original bid. Currently has a winning bid of {new_bid} and was given a bid of {self.winning_bid}.")
        if new_bid > self.winning_bid:
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
        task = MeasurementTask(**self.task)
        split_id = task.id.split('-')
        line_data = [split_id[0], self.subtask_index, self.main_measurement, self.dependencies, task.pos, self.bidder, round(self.own_bid, 3), self.winner, round(self.winning_bid, 3), round(self.t_img, 3), round(self.t_violation, 3), self.bid_solo, self.bid_any]
        out = ""
        for i in range(len(line_data)):
            line_datum = line_data[i]
            out += str(line_datum)
            if i < len(line_data) - 1:
                out += ','

        return out

    def copy(self) -> object:
        return SubtaskBid(  **self.to_dict() )

    def subtask_bids_from_task(task : MeasurementTask, bidder : str) -> list:
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
        return self.winner != TaskBid.NONE

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

    def check_constraints(self, others : list, t : Union[int, float]) -> object:
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
        temp_sat = self.__temp_sat(others, t)

        if not mutex_sat or not dep_sat or not temp_sat:
            # self.reset(t)
            if self.is_optimistic():
                self.bid_any -= 1
                self.bid_any = self.bid_any if self.bid_any > 0 else 0

                self.bid_solo -= 1
                self.bid_solo = self.bid_solo if self.bid_solo >= 0 else 0
            
            return self

        return None

    def __mutex_sat(self, others : list, _ : Union[int, float]) -> bool:
        """
        Checks for mutually exclusive dependency satisfaction
        """
        # for other in others:
        #     other : SubtaskBid
        #     if other.subtask_index == self.subtask_index:
        #         continue

        #     if  other.winning_bid <= self.winning_bid and other.dependencies[self.subtask_index] < 0:
        #         return False

        # return True
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
        task = MeasurementTask(**self.task)
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

            tie_breaker = self.is_optimistic() and (self.t_img > other.t_img)

            if not corr_time_met and not independent and not tie_breaker:
                return False
        
        return True

class ACCBBAPlannerModule(ACBBAPlannerModule):
    """
    # Asynchronous Consensus Constraint-Based Bundle Algorithm Planner
    """
    def __init__(   self, 
                    results_path: str, 
                    manager_port: int, 
                    agent_id: int, 
                    parent_network_config: NetworkConfig, 
                    l_bundle: int, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:
        """
        Creates an intance of an ACCBBA Planner Module

        ### Arguments:
            - results_path (`str`): path for printing this planner's results
            - manager_port (`int`): localhost port used by the parent agent
            - agent_id (`int`): iddentification number for the parent agent
            - parent_network_config (:obj:`NetworkConfig`): network config of the parent agent
            - l_bundle (`int`): maximum bundle size
            - level (`int`): logging level
            - logger (`logging.Logger`): logger being used 
        """
        super().__init__(results_path, manager_port, agent_id, parent_network_config, l_bundle, PlannerTypes.ACCBBA, level, logger)
        self.planner_type = PlannerTypes.ACCBBA

        self.stats = {
                        "consensus" : [],
                        "planning" : [],
                        "doing" : [],
                        "c_comp_check" : [],
                        "c_tend_check" : [],
                        "c_const_check" : []
                    }
        self.plan_history = []
        self.iter_counter = 0

    async def listener(self):
        """
        ## Listener 

        Listen for any messages from the parent agent and adjust its results ledger.
        Any relevant bids that may affect the bundle, along with any changes in state or 
        task completion status are forwarded to the bundle builder.
        """
        # 
        try:
            # initiate results tracker
            results = {}
            t_curr = 0.0

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                    return

                elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!")

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)     

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                            # unpack message 
                            action_msg = AgentActionMessage(**sense)
                            self.log(f"received agent action of status {action_msg.status}! sending to bundle-builder...")
                            
                            # send to bundle builder 
                            await self.action_status_inbox.put(action_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                            # unpack message 
                            state_msg : AgentStateMessage = AgentStateMessage(**sense)
                            self.log(f"received agent state message! sending to bundle-builder...")
                            
                            # update current time:
                            state = SimulationAgentState(**state_msg.state)
                            if t_curr < state.t:
                                t_curr = state.t

                            # send to bundle builder 
                            await self.states_inbox.put(state_msg) 

                        elif sense['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                            # unpack message
                            task_req = TaskRequestMessage(**sense)
                            task_dict : dict = task_req.task
                            task = MeasurementTask(**task_dict)

                            # check if task has already been received
                            if task.id in results:
                                self.log(f"received task request of an already registered task. Ignoring request...")
                                continue
                            
                            # create task bid from task request and add to results
                            self.log(f"received new task request! Adding to results ledger...")

                            bids = SubtaskBid.subtask_bids_from_task(task, self.get_parent_name())
                            results[task.id] = bids

                            # send to bundle-builder and rebroadcaster
                            for bid in bids:
                                out_msg = TaskBidMessage(   
                                                            self.get_element_name(), 
                                                            self.get_parent_name(), 
                                                            bid.to_dict()
                                                        )                            
                            
                                await self.relevant_changes_inbox.put(out_msg)
                                # await self.outgoing_listen_inbox.put(out_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.TASK_BID.value:
                            # unpack message 
                            bid_msg  = TaskBidMessage(**sense)
                            
                            their_bid = SubtaskBid(**bid_msg.bid)

                            if their_bid.bidder == self.get_parent_name():
                                continue

                            self.log(f"received a bid from another agent for task {their_bid.task_id}!")
                            
                            await self.relevant_changes_inbox.put(bid_msg)

                else:
                    self.log(f"received manager broadcast or type {content['msg_type']}! ignoring...")
        
        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results
        
    async def bundle_builder(self) -> None:
        """
        ## Bundle-builder

        Performs periodic checks on the received messages from the listener and
        creates a plan based.
        """
        results = {}
        bundle = []
        path = []
        t_curr = 0.0
        t_next = 0.0
        f_update = 4
        plan = []
        converged = 0
        level = logging.WARNING

        try:
            while True:
                # wait for next periodict check
                state_msg : AgentStateMessage = await self.states_inbox.get()
                state = SimulationAgentState(**state_msg.state)
                t_curr = state.t
                await self.update_current_time(t_curr)
                
                # TODO add fixed periodic checking of messages
                # if t_curr < t_next:
                #     # update threshold has not been reached yet; instruct agent to wait for messages
                #     action = WaitForMessages(t_curr, t_next)
                #     await self.outgoing_bundle_builder_inbox.put(action)
                #     continue

                # # set next update time
                # t_next += 1/f_update
                
                # if self.relevant_changes_inbox.empty():
                #     # if no relevant messages have been received by the update time; wait for next update time
                #     action = WaitForMessages(t_curr, t_next)
                #     await self.outgoing_bundle_builder_inbox.put(action)
                #     continue
                
                # t_update = t_curr

                # update bundle from new information
                t_0 = time.perf_counter()
                results, bundle, path, changes, rebroadcasts = await self.consensus_phase(results, bundle, path, t_curr, level)
                results : dict; bundle : list; path : list; changes : list; rebroadcasts : list
                changes = []
                dt = time.perf_counter() - t_0
                self.stats['consensus'].append(dt)

                self.log_changes("CHANGES MADE FROM CONSENSUS", changes, level)

                if t_curr > 0.0 and len(changes) > 0:
                    x = 1

                t_0 = time.perf_counter()
                results, bundle, path, planner_changes = await self.planning_phase(state, results, bundle, path, level)
                planner_changes : list
                changes.extend(planner_changes)
                rebroadcasts.extend(planner_changes)
                dt = time.perf_counter() - t_0
                self.stats['planning'].append(dt)

                self.log_changes("CHANGES MADE FROM PLANNING", planner_changes, level)

                if t_curr > 0.0 and len(changes) > 0:
                    x = 1

                t_0 = time.perf_counter()
                bundle, path, plan, actions, converged = await self.doing_phase(state, results, bundle, path, plan, changes, t_curr, f_update, converged)
                actions : list    
                dt = time.perf_counter() - t_0
                self.stats['doing'].append(dt)

                # send actions to broadcaster
                rebroadcast_dicts = [rebroadcast.to_dict() for rebroadcast in rebroadcasts]
                action_dicts = [action.to_dict() for action in actions]
                action_dicts.extend(rebroadcast_dicts)
                action_bus = BusMessage(self.get_element_name(), self.get_element_name(), action_dicts)
                await self.outgoing_bundle_builder_inbox.put(action_bus)

                # if len(changes) > 0:
                self.iter_counter += 1
                
        except asyncio.CancelledError:
            return

        finally:
            self.bundle_builder_results = results

    async def consensus_phase(self, results : dict, bundle : list, path : list, t : Union[int, float], level : int = logging.DEBUG) -> None:
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
        results, bundle, path, comp_changes, comp_rebroadcasts, bids_received = await self.compare_results(results, bundle, path, t, level)
        changes.extend(comp_changes)
        rebroadcasts.extend(comp_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_comp_check'].append(dt)

        self.log_results('BIDS RECEIVED', bids_received, level)
        self.log_results('COMPARED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)
        
        # check for expired tasks
        t_0 = time.perf_counter()
        results, bundle, path, exp_changes = await self.check_task_end_time(results, bundle, path, t, level)
        changes.extend(exp_changes)
        rebroadcasts.extend(exp_changes)
        dt = time.perf_counter() - t_0
        self.stats['c_tend_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check task constraint satisfaction
        t_0 = time.perf_counter()
        results, bundle, path, cons_changes = await self.check_results_constraints(results, bundle, path, t, level)
        changes.extend(cons_changes)
        rebroadcasts.extend(cons_changes)
        dt = time.perf_counter() - t_0
        self.stats['c_const_check'].append(dt)

        self.log_results('CONSTRAINT CHECKED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes, rebroadcasts

    async def compare_results(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
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
        bids_received = {}
        while not self.relevant_changes_inbox.empty():
            # get next bid
            bid_msg : TaskBidMessage = await self.relevant_changes_inbox.get()
            
            # unpackage bid
            their_bid = SubtaskBid(**bid_msg.bid)
            if their_bid.task_id not in bids_received:
                bids_received[their_bid.task_id] = {}
            bids_received[their_bid.task_id][their_bid.subtask_index] = their_bid
            
            # check if bid exists for this task
            new_task = their_bid.task_id not in results
            if new_task:
                # was not aware of this task; add to results as a blank bid
                task = MeasurementTask(**their_bid.task)
                results[their_bid.task_id] = SubtaskBid.subtask_bids_from_task(task, self.get_parent_name())

            # compare bids
            my_bid : SubtaskBid = results[their_bid.task_id][their_bid.subtask_index]
            self.log(f'comparing bids...\nmine:  {str(my_bid)}\ntheirs: {str(their_bid)}', level=logging.DEBUG)

            broadcast_bid, changed  = my_bid.update(their_bid.to_dict(), t)
            broadcast_bid : SubtaskBid; changed : bool

            self.log(f'\nupdated: {my_bid}\n', level=logging.DEBUG)
            results[their_bid.task_id][their_bid.subtask_index] = my_bid
                
            # if relevant changes were made, add to changes broadcast
            if broadcast_bid or new_task:                    
                broadcast_bid = broadcast_bid if not new_task else my_bid
                out_msg = TaskBidMessage(   
                                        self.get_parent_name(), 
                                        self.get_parent_name(), 
                                        broadcast_bid.to_dict()
                                    )
                rebroadcasts.append(out_msg)

            if changed or new_task:
                changed_bid = broadcast_bid if not new_task else my_bid
                out_msg = TaskBidMessage(   
                                        self.get_parent_name(), 
                                        self.get_parent_name(), 
                                        changed_bid.to_dict()
                                    )
                changes.append(out_msg)

            # if outbid for a task in the bundle, release subsequent tasks in bundle and path
            bid_task = MeasurementTask(**my_bid.task)
            if (bid_task, my_bid.subtask_index) in bundle and my_bid.winner != self.get_parent_name():
                bid_index = bundle.index((bid_task, my_bid.subtask_index))

                for _ in range(bid_index, len(bundle)):
                    # remove all subsequent tasks from bundle
                    measurement_task, subtask_index = bundle.pop(bid_index)
                    path.remove((measurement_task, subtask_index))

                    # if the agent is currently winning this bid, reset results
                    current_bid : SubtaskBid = results[measurement_task.id][subtask_index]
                    if current_bid.winner == self.get_parent_name():
                        current_bid.reset(t)
                        results[measurement_task.id][subtask_index] = current_bid

                    # self.log_results('PRELIMINARY COMPARED RESULTS', results, level)
                    # self.log_task_sequence('bundle', bundle, level)
                    # self.log_task_sequence('path', path, level)
        
        return results, bundle, path, changes, rebroadcasts, bids_received

    async def check_task_end_time(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.DEBUG) -> tuple:
        """
        Checks if tasks have expired and cannot be performed

        ### Returns
            - results
            - bundle
            - path
            - changes
        """
        changes = []
        # release tasks from bundle if t_end has passed
        task_to_remove = None
        for task, subtask_index in bundle:
            task : MeasurementTask
            if task.t_end - task.duration < t:
                task_to_remove = (task, subtask_index)
                break

        if task_to_remove is not None:
            bundle_index = bundle.index(task_to_remove)
            for _ in range(bundle_index, len(bundle)):
                # remove task from bundle and path
                task, subtask_index = bundle.pop(bundle_index)
                path.remove((task, subtask_index))

                self.log_results('PRELIMINARY CHECKED EXPIRATION RESULTS', results, level)
                self.log_task_sequence('bundle', bundle, level)
                self.log_task_sequence('path', path, level)

        return results, bundle, path, changes


    async def check_results_constraints(self, results : dict, bundle : list, path : list, t : Union[int, float], level=logging.WARNING) -> tuple:
        """
        Looks for tasks that do not have their constraints satisfied
        """
        changes = []          
        while True:
            # find tasks with constraint violations
            task_to_remove = None
            for task, subtask_index in bundle:
                task : MeasurementTask; subtask_index : int
                bid : SubtaskBid = results[task.id][subtask_index]
               
                reset_bid = bid.check_constraints(results[task.id], t)
                if reset_bid is not None:
                    task_to_remove = (task, subtask_index)
                    results[task.id][subtask_index] = reset_bid
                    break
                                
            if task_to_remove is None:
                # all bids satisfy their constraints
                break 

            bundle_index = bundle.index(task_to_remove)
            for _ in range(bundle_index, len(bundle)):
                # remove task from bundle and path
                task, subtask_index = bundle.pop(bundle_index)
                path.remove((task, subtask_index))

                # reset bid
                task : MeasurementTask
                current_bid : SubtaskBid = results[task.id][subtask_index]
                current_bid.reset(t)
                results[task.id][subtask_index] = current_bid

                # register change in results
                out_msg = TaskBidMessage(   
                                        self.get_parent_name(), 
                                        self.get_parent_name(), 
                                        current_bid.to_dict()
                                    )
                changes.append(out_msg)

                # self.log_results('PRELIMINARY CONSTRAINT CHECKED RESULTS', results, level)
                # self.log_task_sequence('bundle', bundle, level)
                # self.log_task_sequence('path', path, level)

        return results, bundle, path, changes
   
    async def planning_phase(self, state : SimulationAgentState, results : dict, bundle : list, path : list, level : int = logging.DEBUG) -> None:
        """
        Uses the most updates results information to construct a path
        """
        available_tasks : list = self.get_available_tasks(state, bundle, results)
        changes = []
        changes_to_bundle = []
        
        current_bids = {task.id : {} for task, _ in bundle}
        for task, subtask_index in bundle:
            task : MeasurementTask
            current_bids[task.id][subtask_index] = results[task.id][subtask_index]

        max_path = [(task, subtask_index) for task, subtask_index in path]; 
        max_path_bids = {task.id : {} for task, _ in path}
        for task, subtask_index in path:
            task : MeasurementTask
            max_path_bids[task.id][subtask_index] = results[task.id][subtask_index]

        max_path_utility = self.sum_path_utility(path, current_bids)
        max_task = -1

        while len(bundle) < self.l_bundle and len(available_tasks) > 0 and max_task is not None:                   
            # find next best task to put in bundle (greedy)
            max_task = None 
            max_subtask = None
            for measurement_task, subtask_index in available_tasks:
                # calculate bid for a given available task
                measurement_task : MeasurementTask
                subtask_index : int
                projected_path, projected_bids, projected_path_utility = self.calc_path_bid(state, results, path, measurement_task, subtask_index)
                
                # check if path was found
                if projected_path is None:
                    continue
                
                # compare to maximum task
                if (max_task is None or projected_path_utility > max_path_utility):

                    # check for cualition and mutex satisfaction
                    proposed_bid :SubtaskBid = projected_bids[measurement_task.id][subtask_index]
                    passed_coalition_test = self.coalition_test(results, proposed_bid)
                    passed_mutex_test = self.mutex_test(results, proposed_bid)
                    if not passed_coalition_test or not passed_mutex_test:
                        # ignore path if proposed bid for any task cannot out-bid current winners
                        continue
                    
                    max_path = projected_path
                    max_task = measurement_task
                    max_subtask = subtask_index
                    max_path_bids = projected_bids
                    max_path_utility = projected_path_utility

            if max_task is not None:
                # max bid found! place task with the best bid in the bundle and the path
                bundle.append((max_task, max_subtask))
                path = max_path

                # remove bid task from list of available tasks
                available_tasks.remove((max_task, max_subtask))
            
            #  update bids
            for measurement_task, subtask_index in path:
                measurement_task : MeasurementTask
                subtask_index : int
                new_bid : TaskBid = max_path_bids[measurement_task.id][subtask_index]
                old_bid : TaskBid = results[measurement_task.id][subtask_index]
                
                if old_bid.task_id != new_bid.task_id:
                    x = 1

                if results[measurement_task.id][subtask_index] != new_bid:
                    changes_to_bundle.append((measurement_task, subtask_index))

                results[measurement_task.id][subtask_index] = new_bid

            # self.log_results('PRELIMINART MODIFIED BUNDLE RESULTS', results, level)
            # self.log_task_sequence('bundle', bundle, level)
            # self.log_task_sequence('path', path, level)

        # broadcast changes to bundle
        for measurement_task, subtask_index in changes_to_bundle:
            measurement_task : MeasurementTask
            subtask_index : int

            new_bid = results[measurement_task.id][subtask_index]

            # add to changes broadcast 
            out_msg = TaskBidMessage(   
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
                task = MeasurementTask(**subtaskbid.task)

                if self.bundle_contains_mutex_subtasks(bundle, task, subtask_index):
                    continue

                is_biddable = self.can_bid(state, task, subtask_index, results[task_id]) 
                already_in_bundle = (task, subtaskbid.subtask_index) in bundle 
                already_performed = state.t > subtaskbid.t_img and subtaskbid.winner != SubtaskBid.NONE
                
                if is_biddable and (not already_in_bundle) and (not already_performed):
                    available.append((task, subtaskbid.subtask_index))

        return available

    def can_bid(self, state : SimulationAgentState, task : MeasurementTask, subtask_index : int, subtaskbids : list) -> bool:
        """
        Checks if an agent has the ability to bid on a measurement task
        """
        # check capabilities - TODO: Replace with knowledge graph
        subtaskbid : SubtaskBid = subtaskbids[subtask_index]
        if subtaskbid.main_measurement not in state.instruments:
            return False 

        # check time constraints
        ## Constraint 1: task must be able to be performed during or after the current time
        if task.t_end < state.t:
            return False
        
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

    def bundle_contains_mutex_subtasks(self, bundle : list, task : MeasurementTask, subtask_index : int) -> bool:
        """
        Returns true if a bundle contains a subtask that is mutually exclusive to a subtask being added

        ### Arguments:
            - bundle (`list`) : current bundle to be expanded
            - task (:obj:`MeasurementTask`) : task to be added to the bundle
            - subtask_index (`int`) : index of the subtask to be added to the bundle
        """
        for task_i, subtask_index_i in bundle:
            task_i : MeasurementTask
            subtask_index_i : int 

            if task_i.id != task.id:
                # subtasks reffer to different tasks, cannot be mutually exclusive
                continue

            if (
                    task_i.dependency_matrix[subtask_index_i][subtask_index] < 0
                or  task_i.dependency_matrix[subtask_index][subtask_index_i] < 0
                ):
                # either the existing subtask in the bundle is mutually exclusive with the subtask to be added or viceversa
                return True
            
        return False

    def sum_path_utility(self, path : list, bids : dict) -> float:
        utility = 0.0
        for task, subtask_index in path:
            task : MeasurementTask
            bid : SubtaskBid = bids[task.id][subtask_index]
            utility += bid.own_bid

        return utility

    def calc_path_bid(
                        self, 
                        state : SimulationAgentState, 
                        original_results : dict,
                        original_path : list, 
                        task : MeasurementTask, 
                        subtask_index : int
                    ) -> tuple:
        winning_path = None
        winning_bids = None
        winning_path_utility = 0.0

        # find best placement in path
        # self.log_task_sequence('original path', original_path, level=logging.WARNING)
        for i in range(len(original_path)+1):
            # generate possible path
            path = [scheduled_task for scheduled_task in original_path]
            
            path.insert(i, (task, subtask_index))
            # self.log_task_sequence('new proposed path', path, level=logging.WARNING)

            # calculate bids for each task in the path
            bids = {}
            for task_i, subtask_j in path:
                # calculate imaging time
                task_i : MeasurementTask
                subtask_j : int
                t_img = self.calc_imaging_time(state, original_results, path, bids, task_i, subtask_j)

                # predict state
                # TODO move state prediction to state class
                path_index = path.index((task_i, subtask_j))
                if path_index == 0:
                    prev_state = state
                else:
                    prev_task, prev_subtask = path[path_index-1]
                    prev_task : MeasurementTask; prev_subtask : int
                    prev_bid : SubtaskBid = bids[prev_task.id][prev_subtask]
                    t_prev = prev_bid.t_img + prev_task.duration
                    prev_state = SimulationAgentState(prev_task.pos,
                                                        state.x_bounds,
                                                        state.y_bounds,
                                                        [0.0, 0.0],
                                                        state.v_max,
                                                        [],
                                                        state.status,
                                                        t_prev,
                                                        state.instruments)

                # calculate bidding score
                utility = self.calc_utility(prev_state, task_i, subtask_j, t_img)

                # create bid
                bid : SubtaskBid = original_results[task_i.id][subtask_j].copy()
                bid.set_bid(utility, t_img, state.t)
                
                if task_i.id not in bids:
                    bids[task_i.id] = {}    
                bids[task_i.id][subtask_j] = bid

            # look for path with the best utility
            path_utility = self.sum_path_utility(path, bids)
            if path_utility > winning_path_utility:
                winning_path = path
                winning_bids = bids
                winning_path_utility = path_utility

        return winning_path, winning_bids, winning_path_utility

    def calc_imaging_time(self, state : SimulationAgentState, current_results : dict, path : list, bids : dict, task : MeasurementTask, subtask_index : int) -> float:
        """
        Computes the earliest time when a task in the path would be performed

        ### Arguments:
            - state (obj:`SimulationAgentState`): state of the agent at the start of the path
            - path (`list`): sequence of tasks dictionaries to be performed
            - bids (`dict`): dictionary of task ids to the current task bid dictionaries 

        ### Returns
            - t_img (`float`): earliest available imaging time
        """
        # calculate the previous task's position and 
        i = path.index((task,subtask_index))
        if i == 0:
            t_prev = state.t
            pos_prev = state.pos
        else:
            task_prev, subtask_index_prev = path[i-1]
            task_prev : MeasurementTask
            subtask_index_prev : int
            bid_prev : Bid = bids[task_prev.id][subtask_index_prev]
            t_prev : float = bid_prev.t_img + task_prev.duration
            pos_prev : list = task_prev.pos

        # compute earliest time to the task
        t_img = state.calc_arrival_time(pos_prev, task.pos, t_prev)
        t_img = t_img if t_img >= task.t_start else task.t_start
        
        # get active time constraints
        t_consts = []
        for subtask_index_dep in range(len(current_results[task.id])):
            dep_bid : SubtaskBid = current_results[task.id][subtask_index_dep]
            
            if dep_bid.winner == SubtaskBid.NONE:
                continue

            if task.dependency_matrix[subtask_index][subtask_index_dep] > 0:
                t_corr = task.time_dependency_matrix[subtask_index][subtask_index_dep]
                t_consts.append((dep_bid.t_img, t_corr))
        
        if len(t_consts) > 0:
            # sort time-constraints in ascending order
            t_consts = sorted(t_consts)

            # check if chosen imaging time satisfies the latest time constraints
            t_const, t_corr = t_consts.pop()
            if t_img + t_corr < t_const:
                # i am performing my measurement before the other agent's earliest time; meet its imaging time
                t_img = t_const - t_corr
            # else:
                # other agent images before my earliest time; expect other bidder to met my schedule
                # or `t_img` satisfies this time constraint; no action required

        return t_img
        
    def calc_utility(   
                        self, 
                        state : SimulationAgentState,
                        task : MeasurementTask, 
                        subtask_index : int, 
                        t_img : float
                    ) -> float:
        """
        Calculates the expected utility of performing a measurement task

        ### Arguments:
            - state (:obj:`SimulationAgentState`): agent state before performing the task
            - task (:obj:`MeasurementTask`): task to be performed 
            - subtask_index (`int`): index of subtask to be performed
            - t_img (`float`): time at which the task will be performed

        ### Retrurns:
            - utility (`float`): estimated normalized utility 
        """
        utility = super().calc_utility(task, t_img)

        _, dependent_measurements = task.measurement_groups[subtask_index]
        k = len(dependent_measurements) + 1

        if k / len(task.measurements) == 1.0:
            alpha = 1.0
        else:
            alpha = 1.0/3.0

        return utility * alpha / k - self.calc_cost(state, task, subtask_index, t_img)
    
    def calc_cost(   
                        self, 
                        state : SimulationAgentState,
                        task : MeasurementTask, 
                        subtask_index : int, 
                        t_img : float
                    ) -> float:
        """
        
        """
        # TODO add cost calculations
        travel_cost = 0

        coalition_formation_cost = 2.0

        coalition_split_cost = 1.0

        intrinsic_cost = 2.0

        return 0.0

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
        current_bid : SubtaskBid = current_results[proposed_bid.task_id][proposed_bid.subtask_index]
        coalition_bid = 0

        for bid_i in current_results[proposed_bid.task_id]:
            bid_i : SubtaskBid
            bid_i_index = current_results[proposed_bid.task_id].index(bid_i)

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
        for bid_i in current_results[proposed_bid.task_id]:
            bid_i : SubtaskBid
            bid_i_index = current_results[proposed_bid.task_id].index(bid_i)

            if bid_i_index == proposed_bid.subtask_index:
                continue

            if proposed_bid.dependencies[bid_i_index] == 1:
                agent_bid += bid_i.winning_bid
                agent_coalition.append(bid_i_index)

        # initiate coalition bid count
        ## find all possible coalitions
        task = MeasurementTask(**proposed_bid.task)
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
                bid_i : SubtaskBid = current_results[proposed_bid.task_id][coalition_member]

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

    async def doing_phase(
                            self, 
                            state : SimulationAgentState, 
                            results : dict, 
                            bundle : list, 
                            path : list, 
                            plan : list, 
                            changes : list, 
                            t_curr : Union[int, float], 
                            f_update : Union[int, float],
                            converged : int
                        ) -> tuple:
        """
        Given the state of the current plan, give the agent tasks to perform
        """
        # give agent tasks to perform at the current time
        actions = []
        if (len(changes) == 0 
            and len(path) > 0
            and self.check_path_constraints(path, results, t_curr)):

            # if converged < 2:
            #     converged += 1

            # elif len(plan) == 0:
            if len(plan) == 0:
                # no itemized plan has been generated yet; generate one
                measurement_plan = []
                for i in range(len(path)):
                    measurement_task, subtask_index = path[i]
                    measurement_task : MeasurementTask; subtask_index : int
                    subtask_bid : SubtaskBid = results[measurement_task.id][subtask_index]
                    
                    if i == 0:
                        t_move_start = t_curr
                        prev_pos = state.pos

                    else:
                        prev_task, prev_subtask_index = path[i-1]
                        prev_task : MeasurementTask; prev_subtask_index : int
                        
                        prev_bid : SubtaskBid = results[prev_task.id][prev_subtask_index]
                        t_move_start = prev_bid.t_img + prev_task.duration
                        prev_pos = prev_task.pos

                    task_pos = measurement_task.pos
                    dx = np.sqrt( (task_pos[0] - prev_pos[0])**2 + (task_pos[1] - prev_pos[1])**2 )
                    t_move_end = t_move_start + dx / state.v_max
                    t_img_start = subtask_bid.t_img
                    t_img_end = t_img_start + measurement_task.duration

                    if isinstance(self._clock_config, FixedTimesStepClockConfig):
                        dt = self._clock_config.dt
                        if t_move_start < np.Inf:
                            t_move_start = dt * math.floor(t_move_start/dt)
                        if t_move_end < np.Inf:
                            t_move_end = dt * math.ceil(t_move_end/dt)

                        if t_img_start < np.Inf:
                            t_img_start = dt * math.floor(t_img_start/dt)
                        if t_img_end < np.Inf:
                            t_img_end = dt * math.ceil(t_img_end/dt)

                    move_action = MoveAction(measurement_task.pos, t_move_start, t_move_end)
                    measurement_action = MeasurementAction( measurement_task.to_dict(),
                                                            subtask_index, 
                                                            subtask_bid.main_measurement,
                                                            subtask_bid.winning_bid,
                                                            t_img_start, 
                                                            t_img_end)

                    # plan per measurement request: move to plan, perform measurement 
                    plan.append(move_action)
                    plan.append(measurement_action)  

                    measurement_plan.append((t_curr, measurement_task, subtask_index, subtask_bid.copy()))
                
                actions.append(plan[0])
                self.plan_history.append(measurement_plan)
            else:
                # plan has already been developed and is being performed; check plan complation status
                x = 1
                while not self.action_status_inbox.empty():
                    action_msg : AgentActionMessage = await self.action_status_inbox.get()
                    performed_action = AgentAction(**action_msg.action)

                    if len(plan) < 1:
                        continue

                    latest_plan_action : AgentAction = plan[0]
                    if performed_action.id != latest_plan_action.id:
                        # some other task was performed; ignoring 
                        continue

                    elif performed_action.status == AgentAction.PENDING:
                        # latest action from plan was attepted but not completed; performing again
                        
                        if t_curr < latest_plan_action.t_start:
                            # if action was not ready to be performed, wait for a bit
                            actions.append( WaitForMessages(t_curr, latest_plan_action.t_start - t_curr) )
                        else:
                            # try to perform action again
                            actions.append(plan[0])

                    elif performed_action.status == AgentAction.COMPLETED or performed_action.status == AgentAction.ABORTED:
                        # latest action from plan was completed! performing next action in plan
                        done_action : AgentAction = plan.pop(0)

                        if done_action.action_type == ActionTypes.MEASURE.value:
                            done_action : MeasurementAction
                            done_task = MeasurementTask(**done_action.task)
                            
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
                
                if len(actions) == 0 and len(plan) > 0:
                    next_task : AgentAction = plan[0]
                    if t_curr >= next_task.t_start:
                        actions.append(next_task)
                    else:
                        actions.append( WaitForMessages(t_curr, next_task.t_start) )

        else:
            # bundle is empty or cannot be executed yet; instructing agent to idle
            plan = []
            converged = 0
                        
        if len(actions) == 0 and len(changes) == 0 and len(plan) == 0:
            actions.append( WaitForMessages(t_curr, t_curr + 1/f_update) )

        return bundle, path, plan, actions, converged

    def check_path_constraints(self, path : list, results : dict, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids of every task in the current path have all of their constraints
        satisfied by other bids.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        for task, subtask_index in path:
            # check constraints
            task : MeasurementTask
            if not self.check_task_constraints(results, task, subtask_index, t_curr):
                return False
            
            # check local convergence
            my_bid : SubtaskBid = results[task.id][subtask_index]
            if t_curr < my_bid.t_update + my_bid.dt_converge:
                return False

        return True

    def check_task_constraints(self, results : dict, task : MeasurementTask, subtask_index : int, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids in the current results satisfy the constraints of a given task.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        bid : SubtaskBid = results[task.id][subtask_index]
        bid_copy : SubtaskBid = bid.copy()
        return bid_copy.check_constraints(results[task.id], t_curr) is None

    async def rebroadcaster(self) -> None:
        """
        ## Rebroadcaster

        Sends out-going mesasges from the bundle-builder and the listener to the parent agent.
        """
        try:
            while True:
                # wait for bundle-builder to finish processing information
                self.log('waiting for bundle-builder...')
                bundle_msgs = []
                bundle_bus : BusMessage = await self.outgoing_bundle_builder_inbox.get()
                for msg_dict in bundle_bus.contents:
                    msg_dict : dict
                    action_type = msg_dict.get('action_type', None)
                    msg_type = msg_dict.get('msg_type', None)

                    if action_type is not None:
                        bundle_msgs.append(action_from_dict(**msg_dict))
                    elif msg_type is not None:
                        bundle_msgs.append(message_from_dict(**msg_dict))

                self.log('bundle-builder sent its messages! comparing bids with listener...')

                # get all messages from listener                
                listener_msgs = []
                while not self.outgoing_listen_inbox.empty():
                    listener_msgs.append(await self.outgoing_listen_inbox.get())

                # compare and classify messages
                bid_messages = {}
                actions = []

                for msg in listener_msgs:
                    if isinstance(msg, TaskBidMessage):
                        bundle_bid : SubtaskBid = SubtaskBid(**msg.bid)
                        if bundle_bid.task_id not in bid_messages:
                            bid_messages[bundle_bid.task_id] = {}
                            bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg

                        elif bundle_bid.subtask_index not in bid_messages[bundle_bid.task_id]:
                            bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg
                            
                        else:
                            # only keep most recent information for bids
                            listener_bid_msg : TaskBidMessage = bid_messages[bundle_bid.task_id][bundle_bid.subtask_index]
                            listener_bid : SubtaskBid = SubtaskBid(**listener_bid_msg.bid)
                            if bundle_bid.t_update >= listener_bid.t_update:
                                bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg

                for msg in bundle_msgs:
                    if isinstance(msg, TaskBidMessage):
                        bundle_bid : SubtaskBid = SubtaskBid(**msg.bid)
                        if bundle_bid.task_id not in bid_messages:
                            bid_messages[bundle_bid.task_id] = {}
                            bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg

                        elif bundle_bid.subtask_index not in bid_messages[bundle_bid.task_id]:
                            bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg

                        else:
                            # only keep most recent information for bids
                            listener_bid_msg : TaskBidMessage = bid_messages[bundle_bid.task_id][bundle_bid.subtask_index]
                            listener_bid : SubtaskBid = SubtaskBid(**listener_bid_msg.bid)
                            if bundle_bid.t_update >= listener_bid.t_update:
                                bid_messages[bundle_bid.task_id][bundle_bid.subtask_index] = msg
                            
                    elif isinstance(msg, AgentAction):
                        actions.append(msg)                        
        
                # build plan
                plan = []
                changes = []
                for task_id in bid_messages:
                    for subtask_index in bid_messages[task_id]:
                        bid_message : TaskBidMessage = bid_messages[task_id][subtask_index]
                        changes.append(bid_message)
                        plan.append(BroadcastMessageAction(bid_message.to_dict()).to_dict())

                for action in actions:
                    action : AgentAction
                    plan.append(action.to_dict())

                self.log_changes("CHANGES TO BE SENT", changes, logging.WARNING)
                
                # send to agent
                self.log(f'bids compared! generating plan with {len(bid_messages)} bid messages and {len(actions)} actions')
                plan_msg = PlanMessage(self.get_element_name(), self.get_parent_name(), plan)
                await self._send_manager_msg(plan_msg, zmq.PUB)
                self.log(f'actions sent!')

        except asyncio.CancelledError:
            pass

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
            for task, subtask_index in sequence:
                task : MeasurementTask
                subtask_index : int
                split_id = task.id.split('-')
                
                if sequence.index((task, subtask_index)) > 0:
                    out += ', '
                out += f'({split_id[0]}, {subtask_index})'
            out += ']\n'

            self.log(out,level)

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
                        task = MeasurementTask(**bid.task)
                        split_id = task.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, task.pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                elif isinstance(results[task_id], dict):
                    for bid_index in results[task_id]:
                        bid : SubtaskBid = results[task_id][bid_index]
                        task = MeasurementTask(**bid.task)
                        split_id = task.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, task.pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                else:
                    raise ValueError(f'`results` must be of type `list` or `dict`. is of type {type(results)}')

            df = DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

    def log_changes(self, dsc : str, changes : list, level=logging.DEBUG) -> None:
        if self._logger.getEffectiveLevel() <= level:
            headers = ['task_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for change in changes:
                change : TaskBidMessage
                bid = SubtaskBid(**change.bid)
                task = MeasurementTask(**bid.task)
                split_id = task.id.split('-')
                line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, task.pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                data.append(line)
        
            df = DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

    async def teardown(self) -> None:
        await super().teardown()

        # log plan history
        out = 'plan_index,t,task_id,subtask_index,t_img,u_exp\n'
        for i in range(len(self.plan_history)):
            for t, task, subtask_index, subtask_bid in self.plan_history[i]:
                task : MeasurementTask
                subtask_index : int
                subtask_bid : SubtaskBid
                
                line_data = [   i,
                                t,
                                task.id.split('-')[0],
                                subtask_index,
                                np.round(subtask_bid.t_img,3 ),
                                np.round(subtask_bid.winning_bid,3)
                ]

                for j in range(len(line_data)):
                    out += str(line_data[j])
                    if j < len(line_data)-1:
                        out += ','
                    else:
                        out += '\n'

        self.log(f'\nPLANNER HISTORY\n{out}', level=logging.WARNING)

        with open(f"{self.results_path}/{self.get_parent_name()}/planner_history.csv", "w") as file:
            file.write(out)