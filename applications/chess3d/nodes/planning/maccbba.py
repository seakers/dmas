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

    async def flush_bids(self) -> list:
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

    async def add_bid(self, new_bid : SubtaskBid) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        await self.bid_access_lock.acquire()

        if new_bid.req_id not in self.bid_buffer:
            req : MeasurementRequest = MeasurementRequest.from_dict(new_bid.req)
            self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

        current_bid : SubtaskBid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]

        if current_bid is None or new_bid.t_update > current_bid.t_update:
            self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()

        self.bid_access_lock.release()

        self.updated.set()
        self.updated.clear()

    async def add_bids(self, new_bids : list) -> None:
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

            if current_bid is None or new_bid.t_update > current_bid.t_update:
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

        return self.flush_bids()


class MACCBBA(MCCBBA):
    
    async def setup(self) -> None:
        await super().setup()

        self.listener_to_builder_buffer = BidBuffer()
        self.listener_to_broadcaster_buffer = BidBuffer()
        self.builder_to_broadcaster_buffer = BidBuffer()

        self.t_curr = 0
        self.current_agent_state : SimulationAgentState = None
        self.parent_agent_type = None
        self.orbitdata = None

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
                            state : SimulationAgentState = SimulationAgentState.from_dict(state_msg.state)

                            self.update_current_time(state.t)
                            self.current_agent_state = state

                            if self.parent_agent_type is None:
                                if isinstance(state, SatelliteAgentState):
                                    # import orbit data
                                    self.orbitdata : OrbitData = self._load_orbit_data()
                                    self.parent_agent_type = SimulationAgentTypes.SATELLITE.value
                                elif isinstance(state, UAVAgentState):
                                    self.parent_agent_type = SimulationAgentTypes.UAV.value
                                else:
                                    raise NotImplementedError(f"states of type {state_msg.state['state_type']} not supported for greedy planners.")

                            await self.states_inbox.put(state_msg) 

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
                                await self.listener_to_builder_buffer.add_bids(bids)
                                await self.listener_to_broadcaster_buffer.add_bids(bids)

                                # inform bundle-builder of new tasks
                                await self.measurement_req_inbox.put(req_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            bid : SubtaskBid = SubtaskBid(**bid_msg.bid)
                            self.log(f"received measurement request message!")
                            
                            # check if bid exists for this task
                            new_req = bid.req_id not in results
                            if new_req:
                                # was not aware of this task; add to results as a blank bid
                                req = MeasurementRequest.from_dict(**req_msg.req)
                                results[bid.req_id] = SubtaskBid.subtask_bids_from_task(req, self.get_parent_name())

                            # compare bids
                            my_bid : SubtaskBid = results[bid.req_id][bid.subtask_index]
                            self.log(f'comparing bids...\nmine:  {str(my_bid)}\ntheirs: {str(bid)}', level=logging.DEBUG)

                            broadcast_bid, _  = my_bid.update(bid.to_dict(), self.get_current_time())
                            broadcast_bid : SubtaskBid

                            self.log(f'\nupdated: {my_bid}\n', level=logging.DEBUG)
                            results[bid.req_id][bid.subtask_index] = my_bid

                            if broadcast_bid or new_req:                    
                                # relevant changes were made
                                broadcast_bid = broadcast_bid if not new_req else my_bid

                                # send to bundle-builder and broadcaster
                                await self.listener_to_builder_buffer.add_bid(broadcast_bid)
                                await self.listener_to_broadcaster_buffer.add_bid(broadcast_bid)

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
                relevant_changes = await self.listener_to_broadcaster_buffer.wait_for_updates()
                self.log_results('BIDS RECEIVED', relevant_changes, level)

                # Consensus Phase 
                t_0 = time.perf_counter()
                results, bundle, path, consensus_changes, consensus_rebroadcasts = await self.consensus_phase(
                                                                                                                results, 
                                                                                                                bundle, 
                                                                                                                path, 
                                                                                                                self.get_current_time,
                                                                                                                relevant_changes ,
                                                                                                                level)
                dt = time.perf_counter() - t_0
                self.stats['consensus'].append(dt)

                # Update iteration counter
                self.iter_counter += 1

                # Planning Phase
                t_0 = time.perf_counter()
                results, bundle, path, planner_changes = await self.planning_phase(self.current_agent_state, results, bundle, path, level)
                dt = time.perf_counter() - t_0
                self.stats['planning'].append(dt)

                self.log_changes("CHANGES MADE FROM PLANNING", planner_changes, level)
                self.log_changes("CHANGES MADE FROM CONSENSUS", consensus_changes, level)

                # Broadcast changes to bundle and any changes from consensus
                broadcast_bids : list = consensus_rebroadcasts
                broadcast_bids.extend(planner_changes)
                self.log_changes("REBROADCASTS TO BE DONE", broadcast_bids, level)
                # wait_for_response = self.has_bundle_dependencies(bundle) and not converged
                # await self.bid_broadcaster(broadcast_bids, self.get_current_time(), wait_for_response, level)
                
                # Check for convergence
                converged = self.path_constraint_sat(path, results, self.get_current_time())
                if converged:
                    # generate plan from path

                    # send plan to broadcaster
                    pass
                

                

        except asyncio.CancelledError:
            return
        finally:
            self.bundle_builder_results = results 


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
        results, bundle, path, exp_changes = await self.check_task_end_time(results, bundle, path, t, level)
        changes.extend(exp_changes)
        rebroadcasts.extend(exp_changes)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

        self.log_results('CHECKED EXPIRATION RESULTS', results, level)
        self.log_task_sequence('bundle', bundle, level)
        self.log_task_sequence('path', path, level)

        # check for already performed tasks
        t_0 = time.perf_counter()
        results, bundle, path, done_changes = await self.check_task_completion(results, bundle, path, t, level)
        changes.extend(done_changes)
        rebroadcasts.extend(done_changes)
        dt = time.perf_counter() - t_0
        self.stats['c_t_end_check'].append(dt)

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
            req = MeasurementRequest.from_dict(their_bid.req)
            new_req = req.id not in results

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
                        
                        out_msg = MeasurementBidMessage(   
                                        self.get_parent_name(), 
                                        self.get_parent_name(), 
                                        current_bid.to_dict()
                                    )
                        rebroadcasts.append(out_msg)
                        changes.append(out_msg)
        
        return results, bundle, path, changes, rebroadcasts

    async def planner(self) -> None:
        try:
            path = []
            results = {}
            reqs_received = []

            while True:
                plan_out = []
                state_msg : AgentStateMessage = await self.states_inbox.get()

                # check time 
                while not self.action_status_inbox.empty():
                    action_msg : AgentActionMessage = await self.action_status_inbox.get()

                    if action_msg.status == AgentAction.PENDING:
                        # if action wasn't completed, re-try
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
                        
                        # print(f'\nACTIONS COMPLETED\tT{t_curr}\nid\taction type\tt_start\tt_end')
                        if removed is not None:
                            removed : AgentAction
                            self.plan : list
                            self.plan.remove(removed)
                            removed = removed.to_dict()
                            # print(removed['id'].split('-')[0], removed['action_type'], removed['t_start'], removed['t_end'])
                        # else:
                        #     print('\n')

                if len(plan_out) == 0 and len(self.plan) > 0:
                    next_action : AgentAction = self.plan[0]
                    if next_action.t_start <= self.get_current_time():
                        plan_out.append(next_action.to_dict())

                # --- FOR DEBUGGING PURPOSES ONLY: ---
                self.log(f'\nPATH\tT{self.get_current_time()}\nid\tsubtask index\tmain mmnt\tpos\tt_img', level=logging.DEBUG)
                out = ''
                for req, subtask_index in path:
                    req : MeasurementRequest; subtask_index : int
                    bid : SubtaskBid = results[req.id][subtask_index]
                    out += f"{req.id.split('-')[0]}, {subtask_index}, {bid.main_measurement}, {req.pos}, {bid.t_img}\n"
                self.log(out, level=logging.DEBUG)

                self.log(f'\nPLAN\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end', level=logging.DEBUG)
                out = ''
                for action in self.plan:
                    action : AgentAction
                    out += f"{action.id.split('-')[0]}, {action.action_type}, {action.t_start}, {action.t_end},\n"
                self.log(out, level=logging.DEBUG)

                self.log(f'\nPLAN OUT\tT{self.get_current_time()}\nid\taction type\tt_start\tt_end', level=logging.DEBUG)
                out = ''
                for action in plan_out:
                    action : dict
                    out += f"{action['id'].split('-')[0]}, {action['action_type']}, {action['t_start']}, {action['t_end']}\n"
                self.log(out, level=logging.DEBUG)
                # -------------------------------------

                if len(plan_out) == 0:
                    # if no plan left, just idle for a time-step
                    self.log('no more actions to perform. instruct agent to idle for the remainder of the simulation.')
                    if len(self.plan) == 0:
                        t_idle = self.get_current_time() + 1e8 # TODO find end of simulation time        
                    else:
                        t_idle = self.plan[0].t_start
                    action = WaitForMessages(self.get_current_time(), t_idle)
                    plan_out.append(action.to_dict())
                    
                self.log(f'sending {len(plan_out)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), plan_out)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return

    async def broadcaster(self) -> None:
        pass