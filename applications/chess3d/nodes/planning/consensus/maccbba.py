import asyncio
from ctypes import Union
import logging
import math
import time
from typing import Any, Callable
import zmq
import numpy as np
import pandas as pd
from applications.chess3d.nodes.orbitdata import OrbitData
from applications.chess3d.nodes.planning.consensus.bids import ConstrainedBid

from nodes.states import *
from nodes.actions import *
from nodes.states import SimulationAgentState
from nodes.science.utility import synergy_factor
from nodes.science.reqs import MeasurementRequest
from nodes.planning.consensus.consesus import ConsensusPlanner
from nodes.planning.consensus.bids import Bid, BidBuffer
from messages import *

from dmas.messages import *

class MACCBBA(ConsensusPlanner):
    async def bundle_builder(self) -> None:
        try:
            results = {}
            path = []
            bundle = []
            converged = False
            level = logging.WARNING
            # level = logging.DEBUG

            while True:
                # wait for incoming bids
                incoming_bids = await self.listener_to_builder_buffer.wait_for_updates()
                self.log_changes('builder - BIDS RECEIVED', incoming_bids, level)

                # Consensus Phase 
                t_0 = time.perf_counter()
                results, bundle, path, consensus_changes, \
                consensus_rebroadcasts = self.consensus_phase(  results, 
                                                                bundle, 
                                                                path, 
                                                                self.get_current_time(),
                                                                incoming_bids,
                                                                'builder',
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
                    # generate plan from path
                    await self.agent_state_lock.acquire()
                    plan = self.plan_from_path(self.agent_state, results, path)
                    self.agent_state_lock.release()

                else:
                    # wait for messages or for next bid time-out
                    t_next = np.Inf
                    for req, subtask_index in path:
                        req : MeasurementRequest
                        bid : ConstrainedBid = results[req.id][subtask_index]

                        if bid.winner == ConstrainedBid.NONE:
                            continue

                        t_timeout = bid.t_violation + bid.dt_violation
                        if t_timeout < t_next:
                            t_next = t_timeout

                    wait_action = WaitForMessages(self.get_current_time(), t_next)
                    plan = [wait_action]
                # converged = self.path_constraint_sat(path, results, self.get_current_time())

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

    """
    -----------------------
        CONSENSUS PHASE
    -----------------------
    """
    def consensus_phase(self, results: dict, bundle: list, path: list, t: Union[int, float], new_bids: list, process_name: str, level: int = logging.DEBUG) -> None:
        results, bundle, path, changes, rebroadcasts = super().consensus_phase(results, bundle, path, t, new_bids, process_name, level)
        results : dict; bundle : list; path : list; changes : list; rebroadcasts : list

        # check task constraint satisfaction
        t_0 = time.perf_counter()
        results, bundle, path, \
            cons_changes, cons_rebroadcasts = self.check_bid_constraints(results, bundle, path, t, level)
        changes.extend(cons_changes)
        rebroadcasts.extend(cons_rebroadcasts)
        dt = time.perf_counter() - t_0
        self.stats['c_const_check'].append(dt)

        self.log_results(f'{process_name} - CONSTRAINT CHECKED RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes, rebroadcasts

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
                bid : ConstrainedBid = results[req.id][subtask_index]
               
                reset_bid, const_failed = bid.check_constraints(results[req.id], t)
                const_failed : ConstrainedBid
                
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
                bid : ConstrainedBid = results[req.id][subtask_index]
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

    def compile_bids(self, bids : list) -> dict:
        rebroadcast_bids = {}

        for bid in bids:
            bid : ConstrainedBid
            
            if bid.req_id not in rebroadcast_bids:
                req = MeasurementRequest.from_dict(bid.req)
                rebroadcast_bids[bid.req_id] = [None for _ in req.dependency_matrix]
            
            current_bid : ConstrainedBid = rebroadcast_bids[bid.req_id][bid.subtask_index]
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
        self.log_results('builder - INITIAL BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        changes = []
        changes_to_bundle = []
        
        current_bids = {task.id : {} for task, _ in bundle}
        for req, subtask_index in bundle:
            req : MeasurementRequest
            current_bid : ConstrainedBid = results[req.id][subtask_index]
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
                    proposed_bid : ConstrainedBid = projected_bids[measurement_req.id][subtask_index]
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

        self.log_results('builder - MODIFIED BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes

    def can_bid(self, state : SimulationAgentState, req : MeasurementRequest, subtask_index : int, subtaskbids : list) -> bool:
        if not super().can_bid(state, req, subtask_index, subtaskbids):
            return False

        ## Constraint 2: coalition constraints
        subtaskbid : ConstrainedBid = subtaskbids[subtask_index]
        n_sat = subtaskbid.count_coal_conts_satisied(subtaskbids)
        if subtaskbid.is_optimistic():
            return (    
                        subtaskbid.N_req == n_sat
                    or  subtaskbid.bid_solo > 0
                    or  (subtaskbid.bid_any > 0 and n_sat > 0)
                    )
        else:
            return subtaskbid.N_req == n_sat

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
            dep_bid : ConstrainedBid = original_results[req.id][subtask_index_dep]
            
            if dep_bid.winner == ConstrainedBid.NONE:
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

            if isinstance(state, UAVAgentState):
                return t_const
        
        elif len(t_imgs) > 0:
            return t_imgs[0]

        return np.Inf

    def coalition_test(self, current_results : dict, proposed_bid : ConstrainedBid) -> float:
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
        current_bid : ConstrainedBid = current_results[proposed_bid.req_id][proposed_bid.subtask_index]
        coalition_bid = 0

        for bid_i in current_results[proposed_bid.req_id]:
            bid_i : ConstrainedBid
            bid_i_index = current_results[proposed_bid.req_id].index(bid_i)

            if (    bid_i.winner == current_bid.winner
                and current_bid.dependencies[bid_i_index] >= 0 ):
                coalition_bid += bid_i.winning_bid

            if (    bid_i.winner == proposed_bid.winner 
                 and proposed_bid.dependencies[bid_i_index] == 1):
                agent_bid += bid_i.winning_bid

        return agent_bid > coalition_bid
    
    def mutex_test(self, current_results : dict, proposed_bid : ConstrainedBid) -> bool:
        # calculate total agent bid count
        agent_bid = proposed_bid.winning_bid
        agent_coalition = [proposed_bid.subtask_index]
        for bid_i in current_results[proposed_bid.req_id]:
            bid_i : ConstrainedBid
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
                bid_i : ConstrainedBid = current_results[proposed_bid.req_id][coalition_member]

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
            my_bid : ConstrainedBid = results[req.id][subtask_index]
            if t_curr < my_bid.t_update + my_bid.dt_converge:
                return False

        return True

    def check_task_constraints(self, results : dict, req : MeasurementRequest, subtask_index : int, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids in the current results satisfy the constraints of a given task.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        bid : ConstrainedBid = results[req.id][subtask_index]
        bid_copy : ConstrainedBid = bid.copy()
        constraint_sat, _ = bid_copy.check_constraints(results[req.id], t_curr)
        return constraint_sat is None

    """
    --------------------
    LOGGING AND TEARDOWN
    --------------------
    """

    def log_changes(self, dsc: str, changes: list, level=logging.DEBUG) -> None:
        if self._logger.getEffectiveLevel() <= level:
            headers = ['req_id', 'i', 'mmt', 'deps', 'location', 'bidder', 'bid', 'winner', 'bid', 't_update', 't_img', 't_v', 'w_solo', 'w_any']
            data = []
            for bid in changes:
                bid : ConstrainedBid
                req = MeasurementRequest.from_dict(bid.req)
                split_id = req.id.split('-')
                line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_update, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                data.append(line)
        
            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

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
                        bid : ConstrainedBid
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                elif isinstance(results[req_id], dict):
                    for bid_index in results[req_id]:
                        bid : ConstrainedBid = results[req_id][bid_index]
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, bid.dependencies, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3), round(bid.t_violation, 3), bid.bid_solo, bid.bid_any]
                        data.append(line)
                else:
                    raise ValueError(f'`results` must be of type `list` or `dict`. is of type {type(results)}')

            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)