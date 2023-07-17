from nodes.planning.mccbba import *


class BidBuffer(object):
    """
    Asynchronous buffer that holds bid information for use by processes within the MACCBBA
    """
    
    def __init__(self) -> None:
        self.bid_access_lock = asyncio.Lock()
        self.bid_buffer = {}
        self.req_access_lock = asyncio.Lock()
        self.req_buffer = []
        self.updated = asyncio.Event()             

    def __len__(self) -> int:
        l = 0
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : SubtaskBid
                l += 1 if bid is not None else 0
        return 1

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

                    # reset bid in buffer
                    subtask_index = self.bid_buffer[req_id].index(bid)
                    self.bid_buffer[req_id][subtask_index] = None

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

        return self.pop_all()


class MACCBBA(MCCBBA):
    
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
            bundle_builder_task = asyncio.create_task(self.planner(), name='bundle_builder()')
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

                            self.update_current_time(state.t)
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
                            req = MeasurementRequest.from_dict(**req_msg.req)
                            self.log(f"received measurement request message!")
                            
                            # if not in send to planner
                            if req.id not in results:
                                # create task bid from measurement request and add to results
                                self.log(f"received new measurement request! Adding to results ledger...")

                                bids : list = SubtaskBid.subtask_bids_from_task(req, self.get_parent_name())
                                results[req.id] = bids

                                # send to bundle-builder and rebroadcaster
                                await self.listener_to_builder_buffer.put_bids(bids)
                                await self.listener_to_broadcaster_buffer.put_bids(bids)

                                # inform bundle-builder of new tasks
                                await self.measurement_req_inbox.put(req_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            bid : SubtaskBid = SubtaskBid(**bid_msg.bid)
                            self.log(f"received measurement request message!")
                            
                            incoming_bids.append(bid)

                    if len(self.broadcasted_bids_buffer) > 0:
                        broadcasted_bids : list = await self.broadcasted_bids_buffer.pop_all()
                        incoming_bids.extend(broadcasted_bids)                    
                    
                    results, bundle, path, \
                    _, rebroadcast_bids = await self.consensus_phase(   results, 
                                                                        bundle, 
                                                                        path, 
                                                                        self.get_current_time(),
                                                                        incoming_bids,
                                                                        logging.DEBUG
                                                                    )

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
            level = logging.DEBUG

            while True:
                # wait for incoming bids
                incoming_bids = await self.listener_to_broadcaster_buffer.wait_for_updates()
                self.log_results('BIDS RECEIVED', incoming_bids, level)

                # # Consensus Phase 
                t_0 = time.perf_counter()
                results, bundle, path, consensus_changes, \
                consensus_rebroadcasts = await self.consensus_phase(    results, 
                                                                        bundle, 
                                                                        path, 
                                                                        self.get_current_time(),
                                                                        incoming_bids,
                                                                        logging.DEBUG
                                                                    )                                                                                                level)
                dt = time.perf_counter() - t_0
                self.stats['consensus'].append(dt)

                # Update iteration counter
                self.iter_counter += 1

                # Planning Phase
                t_0 = time.perf_counter()
                results, bundle, path, planner_changes = await self.planning_phase(self.agent_state, results, bundle, path, level)
                dt = time.perf_counter() - t_0
                self.stats['planning'].append(dt)

                self.log_changes("CHANGES MADE FROM PLANNING", planner_changes, level)
                self.log_changes("CHANGES MADE FROM CONSENSUS", consensus_changes, level)
                
                # Check for convergence
                converged = self.path_constraint_sat(path, results, self.get_current_time())
                if converged:
                    # generate plan from path
                    await self.agent_state_lock.acquire()
                    plan = self.plan_from_path(self.states_inbox, results, path)
                    self.agent_state_lock.release()

                else:
                    # wait for messages or for next bid time-out
                    t_next = np.NINF
                    for req, subtask_index in path:
                        req : MeasurementRequest
                        bid : SubtaskBid = results[req.id][subtask_index]

                        t_timeout = bid.t_violation + bid.dt_violation
                        if t_timeout < t_next:
                            t_next = t_timeout

                    wait_action = WaitForMessages(self.get_current_time(), t_next)
                    plan = [wait_action]
                    
                # Send plan to broadcaster
                await self.plan_inbox.put(plan)

                # Broadcast changes to bundle and any changes from consensus
                broadcast_bids : list = consensus_rebroadcasts
                broadcast_bids.extend(planner_changes)
                
                self.log_changes("REBROADCASTS TO BE DONE", broadcast_bids, level)
                await self.builder_to_broadcaster_buffer.put_bids(broadcast_bids)                                

        except asyncio.CancelledError:
            return
        finally:
            self.bundle_builder_results = results 

    async def planner(self) -> None:
        try:
            plan = []

            while True:
                # wait for agent to update state
                _ : AgentStateMessage = await self.states_inbox.get()

                # --- Look for Plan Updates ---

                # Check if relevant changes to the bundle were performed
                if len(self.listener_to_broadcaster_buffer) > 0:
                    # wait for plan to be updated
                    plan : list = await self.plan_inbox.get()

                    # compule updated bids from the listener and bundle buiilder
                    rebroadcast_bids = {}
                    bids = []

                    # received bids to rebroadcast from bundle-builder
                    bids.extend(self.builder_to_broadcaster_buffer.pop_all())

                    # communicate updates to listener
                    self.broadcasted_bids_buffer.put_bids(bids)
                    
                    # received bids to rebroadcast from listener    
                    bids.extend(self.listener_to_broadcaster_buffer.pop_all())

                    # add bid broadcasts to plan
                    rebroadcast_bids = self.compile_bids(bids)
                    for req_id in rebroadcast_bids:
                        for bid in rebroadcast_bids[req_id]:
                            bid : SubtaskBid
                            if bid is not None:
                                bid_message = MeasurementBidMessage(self.get_parent_name(), self.get_parent_name(), bid.to_dict())
                                plan.insert(0, BroadcastMessageAction(bid_message.to_dict(), self.get_current_time()).to_dict())
                                 
                # --- Execute plan ---

                # check plan completion 
                plan_out = []
                while not self.action_status_inbox.empty():
                    action_msg : AgentActionMessage = await self.action_status_inbox.get()

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

                if len(plan_out) == 0:
                    if len(self.plan) > 0:
                        next_action : AgentAction = self.plan[0]
                        if next_action.t_start <= self.get_current_time():
                            plan_out.append(next_action.to_dict())
                        else:
                            t_idle = next_action.t_start
                            action = WaitForMessages(self.get_current_time(), t_idle)
                            plan_out.append(action.to_dict())
                    else:
                        # no more actions to perform, idle until the end of the simulation
                        self.log('no more actions to perform. instruct agent to idle for the remainder of the simulation.')
                        t_idle = self.get_current_time() + 1e9
                        action = WaitForMessages(self.get_current_time(), t_idle)
                        plan_out.append(action.to_dict())

                # # --- FOR DEBUGGING PURPOSES ONLY: ---
                # self.log(f'\nPATH\tT{self.get_current_time()}\nid\tsubtask index\tmain mmnt\tpos\tt_img', level=logging.DEBUG)
                # out = ''
                # for req, subtask_index in path:
                #     req : MeasurementRequest; subtask_index : int
                #     bid : SubtaskBid = results[req.id][subtask_index]
                #     out += f"{req.id.split('-')[0]}, {subtask_index}, {bid.main_measurement}, {req.pos}, {bid.t_img}\n"
                # self.log(out, level=logging.DEBUG)

                # self.log(f'\nPLAN\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end', level=logging.DEBUG)
                # out = ''
                # for action in self.plan:
                #     action : AgentAction
                #     out += f"{action.id.split('-')[0]}, {action.action_type}, {action.t_start}, {action.t_end},\n"
                # self.log(out, level=logging.DEBUG)

                # self.log(f'\nPLAN OUT\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end', level=logging.DEBUG)
                # out = ''
                # for action in plan_out:
                #     action : dict
                #     out += f"{action['id'].split('-')[0]}, {action['action_type']}, {action['t_start']}, {action['t_end']}\n"
                # self.log(out, level=logging.DEBUG)
                # # -------------------------------------

                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

    def compile_bids(self, bids : list) -> dict:
        rebroadcast_bids = {}

        for bid in bids:
            bid : SubtaskBid
            
            if bid.req not in rebroadcast_bids:
                req = MeasurementRequest.from_dict(bid.req)
                rebroadcast_bids[bid.req_id] = [None for _ in req.dependency_matrix]
            
            current_bid : SubtaskBid = rebroadcast_bids[bid.req_id][bid.subtask_index]
            if (current_bid is None or current_bid.t_update <= bid.t_update):
                rebroadcast_bids[bid.req_id][bid.subtask_index] = bid

        return rebroadcast_bids