
import asyncio
import logging
import time
from typing import Union
import numpy as np
import pandas as pd

from applications.chess3d.nodes.planning.consensus.bids import BidBuffer, UnconstrainedBid
from applications.chess3d.nodes.science.reqs import MeasurementRequest
from applications.chess3d.nodes.states import SimulationAgentState
from applications.planning.actions import WaitForMessages
from nodes.planning.consensus.consesus import ConsensusPlanner


class ACBBA(ConsensusPlanner):
    async def bundle_builder(self) -> None:
        try:
            results = {}
            path = []
            bundle = []; prev_bundle = []
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
                if self.compare_bundles(bundle, prev_bundle):                    
                    # generate plan from path
                    await self.agent_state_lock.acquire()
                    plan = self.plan_from_path(self.agent_state, results, path)
                    self.agent_state_lock.release()

                else:
                    # wait for messages or for next bid time-out
                    t_next = np.Inf
                    wait_action = WaitForMessages(self.get_current_time(), t_next)
                    plan = [wait_action]
                
                # save previous bundle for future convergence checks
                prev_bundle = []
                for req, subtask in bundle:
                    prev_bundle.append((req, subtask))

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
            current_bid : UnconstrainedBid = results[req.id][subtask_index]
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
                    proposed_bid : UnconstrainedBid = projected_bids[measurement_req.id][subtask_index]
                    
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
                new_bid : UnconstrainedBid = max_path_bids[measurement_req.id][subtask_index]
                old_bid : UnconstrainedBid = results[measurement_req.id][subtask_index]

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
            headers = ['req_id', 'i', 'mmt', 'location', 'bidder', 'bid', 'winner', 'bid', 't_img']
            data = []
            for req_id in results:
                if isinstance(results[req_id], list):
                    for bid in results[req_id]:
                        bid : UnconstrainedBid
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3)]
                        data.append(line)
                elif isinstance(results[req_id], dict):
                    for bid_index in results[req_id]:
                        bid : UnconstrainedBid = results[req_id][bid_index]
                        req = MeasurementRequest.from_dict(bid.req)
                        split_id = req.id.split('-')
                        line = [split_id[0], bid.subtask_index, bid.main_measurement, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_img, 3)]
                        data.append(line)
                else:
                    raise ValueError(f'`results` must be of type `list` or `dict`. is of type {type(results)}')

            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)

    def log_changes(self, dsc: str, changes: list, level=logging.DEBUG) -> None:
        if self._logger.getEffectiveLevel() <= level:
            headers = ['req_id', 'i', 'mmt', 'location', 'bidder', 'bid', 'winner', 'bid', 't_update', 't_img']
            data = []
            for bid in changes:
                bid : UnconstrainedBid
                req = MeasurementRequest.from_dict(bid.req)
                split_id = req.id.split('-')
                line = [split_id[0], bid.subtask_index, bid.main_measurement, req.lat_lon_pos, bid.bidder, round(bid.own_bid, 3), bid.winner, round(bid.winning_bid, 3), round(bid.t_update, 3), round(bid.t_img, 3)]
                data.append(line)
        
            df = pd.DataFrame(data, columns=headers)
            self.log(f'\n{dsc} [Iter {self.iter_counter}]\n{str(df)}\n', level)