from abc import abstractmethod
import asyncio
import logging
import math
import time
from typing import Any, Callable, Union
import pandas as pd
import zmq
from nodes.orbitdata import OrbitData
from nodes.planning.consensus.bids import Bid

from nodes.science.reqs import MeasurementRequest
from messages import *
from dmas.network import NetworkConfig
from nodes.states import *
from nodes.planning.consensus.bids import BidBuffer
from nodes.planning.planners import PlanningModule


class ConsensusPlanner(PlanningModule):
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

        self.replan = asyncio.Event()

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
            level = logging.WARNING
            # level = logging.DEBUG

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

                                bids : list = self.generate_bids_from_request(req)
                                incoming_bids.extend(bids)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            bid : Bid = Bid.from_dict(bid_msg.bid)
                            self.log(f"received measurement request message!")
                            
                            incoming_bids.append(bid)              
                    
                    if len(incoming_bids) > 0:
                        sorting_buffer = BidBuffer()
                        await sorting_buffer.put_bids(incoming_bids)
                        incoming_bids = await sorting_buffer.pop_all()

                        await self.listener_to_builder_buffer.put_bids(incoming_bids)
                        await self.listener_to_broadcaster_buffer.put_bids(incoming_bids)

                    # inform planner of state update
                    self.agent_state_updated.set()
                    self.agent_state_updated.clear()
                    
                    await self.states_inbox.put(state) 

        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results    
    
    @abstractmethod
    def generate_bids_from_request(self, req : MeasurementRequest) -> list:
        pass

    @abstractmethod
    async def bundle_builder(self) -> None:
        """
        Waits for incoming bids to re-evaluate its current plan
        """
        pass

    async def planner(self) -> None:
        try:
            plan = []
            level = logging.WARNING
            # level = logging.DEBUG

            while True:
                # wait for agent to update state
                _ : AgentStateMessage = await self.states_inbox.get()

                # --- Check Action Completion ---
                x = 1
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
                        if action_msg.status == AgentAction.COMPLETED:
                            self.log(f'action of type `{action.action_type}` completed!', level)
                            x = 1

                        action_dict : dict = action_msg.action
                        completed_action = AgentAction(**action_dict)
                        removed = None
                        for action in plan:
                            action : AgentAction
                            if action.id == completed_action.id:
                                removed = action
                                break
                        
                        if removed is not None:
                            removed : AgentAction
                            plan : list
                            plan.remove(removed)
                            # removed = removed.to_dict()

                            # if (isinstance(removed, MeasurementAction) 
                            #     and action_msg.status == AgentAction.COMPLETED):
                            #     req : MeasurementRequest = MeasurementRequest.from_dict(removed.measurement_req)
                            #     bids : list = self.generate_bids_from_request(req)
                            #     bid : Bid = bids[removed.subtask_index]
                            #     bid.set_performed(self.get_current_time())

                            #     await self.listener_to_builder_buffer.put_bid(bid)

                            if (isinstance(removed, BroadcastMessageAction) 
                                and action_msg.status == AgentAction.COMPLETED):
                                bid_msg = MeasurementBidMessage(**removed.msg)
                                bid : Bid = Bid.from_dict(bid_msg.bid)
                                bid.set_performed(self.get_current_time())

                                await self.listener_to_builder_buffer.put_bid(bid)
                
                # --- Look for Plan Updates ---

                plan_out = []
                # Check if relevant changes to the bundle were performed
                if len(self.listener_to_builder_buffer) > 0:
                    # wait for plan to be updated
                    self.replan.set(); self.replan.clear()
                    plan : list = await self.plan_inbox.get()

                    # compule updated bids from the listener and bundle buiilder
                    if len(self.builder_to_broadcaster_buffer) > 0:
                        # received bids to rebroadcast from bundle-builder
                        builder_bids : list = await self.builder_to_broadcaster_buffer.pop_all()
                                                
                        # flush bids from listener    
                        _ = await self.listener_to_broadcaster_buffer.pop_all()

                        # compile bids to be rebroadcasted
                        rebroadcast_bids : list = builder_bids.copy()
                        self.log_changes("planner - REBROADCASTS TO BE DONE", rebroadcast_bids, level)
                        
                        # create message broadcasts for every bid
                        for rebroadcast_bid in rebroadcast_bids:
                            rebroadcast_bid : Bid
                            bid_message = MeasurementBidMessage(self.get_parent_name(), self.get_parent_name(), rebroadcast_bid.to_dict())
                            plan_out.append( BroadcastMessageAction(bid_message.to_dict(), self.get_current_time()).to_dict() )
                    else:
                        # flush redundant broadcasts from listener
                        _ = await self.listener_to_broadcaster_buffer.pop_all()

                # --- Execute plan ---

                # get next action to perform
                plan_out_ids = [action['id'] for action in plan_out]
                if len(plan_out_ids) > 0:
                    for action in plan:
                        action : AgentAction
                        if (action.t_start <= self.get_current_time()
                            and action.id not in plan_out_ids):
                            plan_out.append(action.to_dict())
                            break
                else:
                    for action in plan:
                        action : AgentAction
                        if (action.t_start <= self.get_current_time()
                            and action.id not in plan_out_ids):
                            plan_out.append(action.to_dict())

                if len(plan_out) == 0:
                    if len(plan) > 0:
                        # next action is yet to start, wait until then
                        next_action : AgentAction = plan[0]
                        t_idle = next_action.t_start if next_action.t_start > self.get_current_time() else self.get_current_time()
                    else:
                        # no more actions to perform, idle until the end of the simulation
                        t_idle = np.Inf

                    action = WaitForMessages(self.get_current_time(), t_idle)
                    plan_out.append(action.to_dict())

                # --- FOR DEBUGGING PURPOSES ONLY: ---
                out = f'\nPLAN\nid\taction type\tt_start\tt_end\n'
                for action in plan:
                    action : AgentAction
                    out += f"{action.id.split('-')[0]}, {action.action_type}, {action.t_start}, {action.t_end}\n"
                self.log(out, level)

                out = f'\nPLAN OUT\nid\taction type\tt_start\tt_end\n'
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
                                process_name : str,
                                level : int = logging.DEBUG
                            ) -> None:
        """
        Evaluates incoming bids and updates current results and bundle
        """
        changes = []
        rebroadcasts = []
        self.log_results(f'\n{process_name} - INITIAL RESULTS', results, level)
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

        self.log_changes(f'{process_name} - BIDS RECEIVED', new_bids, level)
        self.log_results(f'{process_name} - COMPARED RESULTS', results, level)
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

        self.log_results(f'{process_name} - CHECKED EXPIRATION RESULTS', results, level)
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

        self.log_results(f'{process_name} - CHECKED EXPIRATION RESULTS', results, level)
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
            their_bid : Bid            

            # check bids are for new requests
            new_req = their_bid.req_id not in results

            req = MeasurementRequest.from_dict(their_bid.req)
            if new_req:
                # was not aware of this request; add to results as a blank bid
                results[req.id] = self.generate_bids_from_request(req)

                # add to changes broadcast
                my_bid : Bid = results[req.id][0]
                rebroadcasts.append(my_bid)
                                    
            # compare bids
            my_bid : Bid = results[their_bid.req_id][their_bid.subtask_index]
            self.log(f'comparing bids...\nmine:  {str(my_bid)}\ntheirs: {str(their_bid)}', level=logging.DEBUG)

            broadcast_bid, changed  = my_bid.update(their_bid.to_dict(), t)
            broadcast_bid : Bid; changed : bool

            self.log(f'\nupdated: {my_bid}\n', level=logging.DEBUG)
            results[their_bid.req_id][their_bid.subtask_index] = my_bid
                
            # if relevant changes were made, add to changes and rebroadcast
            if changed or new_req:
                changed_bid : Bid = broadcast_bid if not new_req else my_bid
                changes.append(changed_bid)

            if broadcast_bid or new_req:                    
                broadcast_bid : Bid = broadcast_bid if not new_req else my_bid
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
                    current_bid : Bid = results[measurement_req.id][subtask_index]
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
                measurement_req : Bid
                current_bid : Bid = results[measurement_req.id][subtask_index]
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
        task_to_reset = None
        for req, subtask_index in bundle:
            req : MeasurementRequest

            # check if bid has been performed 
            subtask_bid : Bid = results[req.id][subtask_index]
            if self.is_bid_completed(req, subtask_bid, t):
                task_to_remove = (req, subtask_index)
                break

            # check if a mutually exclusive bid has been performed
            for subtask_bid in results[req.id]:
                subtask_bid : Bid

                bids : list = results[req.id]
                bid_index = bids.index(subtask_bid)
                bid : Bid = bids[bid_index]

                if self.is_bid_completed(req, bid, t) and req.dependency_matrix[subtask_index][bid_index] < 0:
                    task_to_remove = (req, subtask_index)
                    task_to_reset = (req, subtask_index) 
                    break   

            if task_to_remove is not None:
                break

        if task_to_remove is not None:
            if task_to_reset is not None:
                bundle_index = bundle.index(task_to_remove)
                
                # level=logging.WARNING
                self.log_results('PRELIMINARY PREVIOUS PERFORMER CHECKED RESULTS', results, level)
                self.log_task_sequence('bundle', bundle, level)
                self.log_task_sequence('path', path, level)

                for _ in range(bundle_index, len(bundle)):
                    # remove task from bundle and path
                    req, subtask_index = bundle.pop(bundle_index)
                    path.remove((req, subtask_index))

                    bid : Bid = results[req.id][subtask_index]
                    bid.reset(t)
                    results[req.id][subtask_index] = bid

                    rebroadcasts.append(bid)
                    changes.append(bid)

                    self.log_results('PRELIMINARY PREVIOUS PERFORMER CHECKED RESULTS', results, level)
                    self.log_task_sequence('bundle', bundle, level)
                    self.log_task_sequence('path', path, level)
            else: 
                # remove performed subtask from bundle and path 
                bundle_index = bundle.index(task_to_remove)
                req, subtask_index = bundle.pop(bundle_index)
                path.remove((req, subtask_index))

                # set bid as completed
                bid : Bid = results[req.id][subtask_index]
                bid.performed = True
                results[req.id][subtask_index] = bid

        return results, bundle, path, changes, rebroadcasts

    def is_bid_completed(self, req : MeasurementRequest, bid : Bid, t : float) -> bool:
        """
        Checks if a bid has been completed or not
        """
        return (bid.t_img >= 0.0 and bid.t_img + req.duration < t) or bid.performed

    """
    -----------------------
        PLANNING PHASE
    -----------------------
    """
    @abstractmethod
    async def planning_phase(self) -> None:
        pass


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
    
    def sum_path_utility(self, path : list, bids : dict) -> float:
        utility = 0.0
        for req, subtask_index in path:
            req : MeasurementRequest
            bid : Bid = bids[req.id][subtask_index]
            utility += bid.own_bid

        return utility

    def get_available_tasks(self, state : SimulationAgentState, bundle : list, results : dict) -> list:
        """
        Checks if there are any tasks available to be performed

        ### Returns:
            - list containing all available and bidable tasks to be performed by the parent agent
        """
        available = []
        for req_id in results:
            for subtask_index in range(len(results[req_id])):
                subtaskbid : Bid = results[req_id][subtask_index]; 
                req = MeasurementRequest.from_dict(subtaskbid.req)

                is_biddable = self.can_bid(state, req, subtask_index, results[req_id]) 
                already_in_bundle = self.check_if_in_bundle(req, subtask_index, bundle)
                already_performed = self.request_has_been_performed(results, req, subtask_index, state.t)
                
                if is_biddable and not already_in_bundle and not already_performed:
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
        subtaskbid : Bid = subtaskbids[subtask_index]
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
        
        return True

    def check_if_in_bundle(self, req : MeasurementRequest, subtask_index : int, bundle : list) -> bool:
        for req_i, subtask_index_j in bundle:
            if req_i.id == req.id and subtask_index == subtask_index_j:
                return True
    
        return False

    def request_has_been_performed(self, results : dict, req : MeasurementRequest, subtask_index : int, t : Union[int, float]) -> bool:
        # check if subtask at hand has been performed
        current_bid : Bid = results[req.id][subtask_index]
        subtask_already_performed = t > current_bid.t_img >= 0 + req.duration and current_bid.winner != Bid.NONE
        if subtask_already_performed or current_bid.performed:
            return True

        # check if a mutually exclusive subtask has already been performed
        for _, subtask_bids in results.items():
            for subtask_bid in subtask_bids:
                subtask_bid : Bid         

                if (
                    t > subtask_bid.t_img + req.duration 
                    and subtask_bid.winner != Bid.NONE
                    and req.dependency_matrix[subtask_index][subtask_bid.subtask_index] < 0
                    ):
                    return True
        
        return False

    """
    ------------------------
        EXECUTION PHASE
    ------------------------
    """
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
            bid : Bid = results[measurement_req.id][subtask_index]
            t_conv = bid.t_update + bid.dt_converge
            if t_conv < t_conv_min:
                t_conv_min = t_conv

        if state.t < t_conv_min:
            plan.append( WaitForMessages(state.t, t_conv_min) )
        else:
            # plan.append( WaitForMessages(state.t, state.t) )
            t_conv_min = state.t

        # add actions per measurement
        for i in range(len(path)):
            measurement_req, subtask_index = path[i]
            measurement_req : MeasurementRequest; subtask_index : int
            subtask_bid : Bid = results[measurement_req.id][subtask_index]

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
            
            if t_move_end < subtask_bid.t_img:
                plan.append( WaitForMessages(t_move_end, subtask_bid.t_img) )
                
            t_img_start = subtask_bid.t_img
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

            # inform others of request completion
            bid : Bid = subtask_bid.copy()
            bid.set_performed(t_img_end)
            plan.append(BroadcastMessageAction(MeasurementBidMessage(   self.get_parent_name(), 
                                                                        self.get_parent_name(),
                                                                        bid.to_dict() 
                                                                    ).to_dict(),
                                                t_img_end
                                                )
                        )
        
        return plan

    """
    --------------------
    LOGGING AND TEARDOWN
    --------------------
    """
    @abstractmethod
    def log_results(self, dsc : str, results : dict, level=logging.DEBUG) -> None:
        """
        Logs current results at a given time for debugging purposes

        ### Argumnents:
            - dsc (`str`): description of what is to be logged
            - results (`dict`): results to be logged
            - level (`int`): logging level to be used
        """
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
            for req, subtask_index in sequence:
                req : MeasurementRequest
                subtask_index : int
                split_id = req.id.split('-')
                
                if sequence.index((req, subtask_index)) > 0:
                    out += ', '
                out += f'({split_id[0]}, {subtask_index})'
            out += ']\n'

            self.log(out,level)

    @abstractmethod
    def log_changes(self, dsc : str, changes : list, level=logging.DEBUG) -> None:
        pass

    def log_plan(self, results : dict, plan : list, t : Union[int, float], level=logging.DEBUG) -> None:
        headers = ['t', 'req_id', 'subtask_index', 't_start', 't_end', 't_img', 'u_exp']
        data = []

        for action in plan:
            if isinstance(action, MeasurementAction):
                req : MeasurementRequest = MeasurementRequest.from_dict(action.measurement_req)
                task_id = req.id.split('-')[0]
                subtask_index : int = action.subtask_index
                subtask_bid : Bid = results[req.id][subtask_index]
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
                subtask_bid : Bid
                
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