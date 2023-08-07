
import asyncio
import logging
import time
from typing import Union
import numpy as np
import pandas as pd

from applications.chess3d.nodes.planning.consensus.bids import BidBuffer, UnconstrainedBid
from applications.chess3d.nodes.science.reqs import GroundPointMeasurementRequest, MeasurementRequest
from applications.chess3d.nodes.science.utility import synergy_factor
from applications.chess3d.nodes.states import SatelliteAgentState, SimulationAgentState, UAVAgentState
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
        Uses the most updated measurement request information to construct a path
        """
        self.log_results('builder - INITIAL BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        changes_to_bundle = []

        available_tasks : list = self.get_available_tasks(state, bundle, results)
        
        current_bids = {req.id : {} for req, _ in bundle}
        for req, subtask_index in bundle:
            req : MeasurementRequest
            current_bid : UnconstrainedBid = results[req.id][subtask_index]
            current_bids[req.id][subtask_index] = current_bid.copy()

        max_path = [(req, subtask_index) for req, subtask_index in path]; 
        max_path_bids = {req.id : {} for req, _ in path}
        for req, subtask_index in path:
            req : MeasurementRequest
            max_path_bids[req.id][subtask_index] = results[req.id][subtask_index]

        max_utility = 0.0
        max_task = -1

        while len(available_tasks) > 0 and max_task is not None:                   
            # find next best task to put in bundle (greedy)
            max_task = None 
            max_subtask = None
            for measurement_req, subtask_index in available_tasks:
                # calculate bid for a given available task
                measurement_req : MeasurementRequest
                subtask_index : int

                if (    
                        isinstance(measurement_req, GroundPointMeasurementRequest) 
                    and isinstance(state, SatelliteAgentState)
                    ):
                    # check if the satellite can observe the GP
                    lat,lon,_ = measurement_req.pos
                    df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, 0.0)
                    if df.empty:
                        continue

                projected_path, projected_bids, projected_path_utility = self.calc_path_bid(state, results, path, measurement_req, subtask_index)

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
                    proposed_bid : UnconstrainedBid = projected_bids[measurement_req.id][subtask_index]
                    
                    max_path = projected_path
                    max_task = measurement_req
                    max_subtask = subtask_index
                    max_path_bids = projected_bids
                    max_path_utility = projected_path_utility
                    max_utility = proposed_bid.winning_bid

            if max_task is not None:
                # max bid found! place task with the best bid in the bundle and the path
                bundle.append((max_task, max_subtask))
                path = max_path

                # # remove bid task from list of available tasks
                # available_tasks.remove((max_task, max_subtask))
            
            #  update bids
            for measurement_req, subtask_index in path:
                measurement_req : MeasurementRequest
                subtask_index : int
                new_bid : UnconstrainedBid = max_path_bids[measurement_req.id][subtask_index]
                old_bid : UnconstrainedBid = results[measurement_req.id][subtask_index]

                if old_bid != new_bid and (measurement_req, subtask_index) not in changes_to_bundle:
                    changes_to_bundle.append((measurement_req, subtask_index))

                results[measurement_req.id][subtask_index] = new_bid

            self.log_results('PRELIMINART MODIFIED BUNDLE RESULTS', results, level)
            self.log_task_sequence('bundle', bundle, level)
            self.log_task_sequence('path', path, level)

            available_tasks : list = self.get_available_tasks(state, bundle, results)

        self.log_results('builder - MODIFIED BUNDLE RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        return results, bundle, path, changes_to_bundle

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
                bid : UnconstrainedBid = original_results[req_i.id][subtask_j].copy()
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


    def calc_imaging_time(self, state : SimulationAgentState, path : list, bids : dict, req : MeasurementRequest, subtask_index : int) -> float:
        """
        Computes the ideal" time when a task in the path would be performed
        ### Returns
            - t_img (`float`): earliest available imaging time
        """
        # calculate the state of the agent prior to performing the measurement request
        i = path.index((req, subtask_index))
        if i == 0:
            t_prev = state.t
            prev_state = state.copy()
        else:
            prev_req, prev_subtask_index = path[i-1]
            prev_req : MeasurementRequest; prev_subtask_index : int
            bid_prev : UnconstrainedBid = bids[prev_req.id][prev_subtask_index]
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

        return self.calc_arrival_times(prev_state, req, t_prev)[0]

    def calc_arrival_times(self, state : SimulationAgentState, req : MeasurementRequest, t_prev : Union[int, float]) -> float:
        """
        Estimates the quickest arrival time from a starting position to a given final position
        """
        if isinstance(req, GroundPointMeasurementRequest):
            # compute earliest time to the task
            if isinstance(state, SatelliteAgentState):
                t_imgs = []
                lat,lon,_ = req.lat_lon_pos
                df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, t_prev)

                for _, row in df.iterrows():
                    t_img = row['time index'] * self.orbitdata.time_step
                    dt = t_img - state.t
                
                    # propagate state
                    propagated_state : SatelliteAgentState = state.propagate(t_img)

                    # compute off-nadir angle
                    thf = propagated_state.calc_off_nadir_agle(req)
                    dth = thf - propagated_state.attitude[0]

                    # estimate arrival time using fixed angular rate TODO change to 
                    if dt >= dth / 1.0: # TODO change maximum angular rate 
                        t_imgs.append(t_img)
                return t_imgs

            elif isinstance(state, UAVAgentState):
                dr = np.array(req.pos) - np.array(state.pos)
                norm = np.sqrt( dr.dot(dr) )
                return [norm / state.max_speed + t_prev]

            else:
                raise NotImplementedError(f"arrival time estimation for agents of type {self.parent_agent_type} is not yet supported.")

        else:
            raise NotImplementedError(f"cannot calculate imaging time for measurement requests of type {type(req)}")       


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