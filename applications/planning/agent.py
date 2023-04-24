import logging
import math
from tasks import *
from dmas.agents import *
from dmas.network import NetworkConfig

from messages import *
from states import *
from planners import *

class SimulationAgent(Agent):
    def __init__(   self, 
                    network_name : str,
                    manager_port : int,
                    id : int,
                    manager_network_config: NetworkConfig, 
                    planner_type: PlannerTypes,
                    initial_state: SimulationAgentState, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None) -> None:
        
        # generate network config 
        agent_network_config = NetworkConfig( 	network_name,
												manager_address_map = {
														zmq.REQ: [f'tcp://localhost:{manager_port}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+1}'],
														zmq.PUSH: [f'tcp://localhost:{manager_port+2}']},
												external_address_map = {
														zmq.REQ: [],
														zmq.PUB: [f'tcp://*:{manager_port+5 + 4*id}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+4}']},
                                                internal_address_map = {
														zmq.REP: [f'tcp://*:{manager_port+5 + 4*id + 1}'],
														zmq.PUB: [f'tcp://*:{manager_port+5 + 4*id + 2}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+5 + 4*id + 3}']
											})
        
        if planner_type is PlannerTypes.ACCBBA:
            planning_module = ACCBBAPlannerModule(manager_port,
                                                    id,
                                                    agent_network_config,
                                                    level,
                                                    logger)
        elif planner_type is PlannerTypes.FIXED:
            planning_module = FixedPlannerModule(manager_port,
                                                 id,
                                                 agent_network_config,
                                                 level,
                                                 logger)
        else:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')

        super().__init__(f'AGENT_{id}', 
                        agent_network_config, 
                        manager_network_config, 
                        initial_state, 
                        # [planning_module], 
                        [],
                        level, 
                        logger)
        self.in_range = {}

    async def setup(self) -> None:
        # nothing to set up
        ##TEMPORARY: Fixed Plan
        self.plan = []
        
        steps = 3
        action = MoveAction([0, steps], 2, 1e6)
        self.plan.append(action.to_dict())

        state_msg = AgentStateMessage(  
                                        self.get_element_name(), 
                                        self.get_network_name(),
                                        self.state.to_dict()
                                    )
        action = BroadcastMessageAction(state_msg, 5, 1e6)
        # self.plan.append(action.to_dict())
    
    async def teardown(self) -> None:
        # print state history
        out = '\nt, pos, vel, status\n'
        for state_dict in self.state.history:
            out += f"{state_dict['t']}, {state_dict['pos']}, {state_dict['vel']}, {state_dict['status']}\n"    

        self.log(out, level=logging.WARNING)

    async def sim_wait(self, delay: float) -> None:
        try:  
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ):
                # desired time not yet reached
                t0 = self.get_current_time()
                tf = t0 + delay

                # check if failure or critical state will be reached first
                t_failure = self.state.predict_failure() 
                t_crit = self.state.predict_critical()
                if t_failure < tf:
                    tf = t_failure
                elif t_crit < tf:
                    tf = t_crit
                
                # wait for time update        
                ignored = []   
                while self.get_current_time() <= t0:
                    # send tic request
                    tic_req = TicRequest(self.get_element_name(), t0, tf)
                    _, _, content = await self.send_manager_message(tic_req)

                    if content['msg_type'] != ManagerMessageTypes.RECEPTION_ACK.value:
                        raise asyncio.CancelledError()

                    self.log(f'tic request for {tf}[s] sent! waiting on toc broadcast...')
                    dst, src, content = await self.manager_inbox.get()
                    
                    if content['msg_type'] == ManagerMessageTypes.TOC.value:
                        # update clock
                        msg = TocMessage(**content)
                        await self.update_current_time(msg.t)
                        self.log(f'toc received! time updated to: {self.get_current_time()}[s]')
                    else:
                        # ignore message
                        self.log(f'some other manager message was received. ignoring...')
                        ignored.append((dst, src, content))

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
        
        finally:
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ) and ignored is not None:
                for dst, src, content in ignored:
                    await self.manager_inbox.put((dst,src,content))

    async def sense(self, statuses: list) -> list:
        # initiate senses array
        senses = []

        # check status of previously performed tasks
        completed = []
        for action, status in statuses:
            # sense and compile updated task status for planner 
            action : AgentAction
            status : str
            msg = AgentActionMessage(   self.get_element_name(), 
                                        self.get_element_name(), 
                                        action.to_dict(),
                                        status)
            senses.append(msg)      

            # compile completed tasks for state tracking
            if status == AgentAction.COMPLETED:
                self.state : SimulationAgentState
                completed.append(action.id)

        # update state
        self.state.update_state(self.get_current_time(), 
                                tasks_performed=completed, 
                                status=SimulationAgentState.SENSING)

        # inform environment of new state
        state_msg = AgentStateMessage(  self.get_element_name(), 
                                        SimulationElementRoles.ENVIRONMENT.value,
                                        self.state.to_dict()
                                    )
        await self.send_peer_message(state_msg)

        # save state as sensed state
        state_msg.dst = self.get_element_name()
        senses.append(state_msg)

        # handle environment updates
        while len(self._external_address_ledger) > 1:
            # wait for environment messages
            _, _, content = await self.environment_inbox.get()

            if content['msg_type'] == SimulationMessageTypes.CONNECTIVITY_UPDATE.value:
                # update connectivity
                msg = AgentConnectivityUpdate(**content)
                if (msg.target not in self.in_range or self.in_range[msg.target] == 0) and msg.connected == 1:
                    self.subscribe_to_broadcasts(msg.target)
                    self.in_range[msg.target] = 1
                elif (msg.target not in self.in_range or self.in_range[msg.target] == 1) and msg.connected == 0:
                    self.unsubscribe_to_broadcasts(msg.target)
                    self.in_range[msg.target] = 0

            elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                # save as senses to forward to planner
                senses.append(TaskRequest(**content))

            elif content['msg_type'] == NodeMessageTypes.RECEPTION_ACK.value:
                # no relevant information was sent by the environment
                break
                
            # give environment time to continue sending any pending messages if any are yet to be transmitted
            await asyncio.sleep(0.01)

            if self.manager_inbox.empty():
                break
        
        # handle peer broadcasts
        while not self.external_inbox.empty():
            _, _, content = await self.external_inbox.get()

            if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                # save as senses to forward to planner
                senses.append(AgentStateMessage(**content))

            elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                # save as senses to forward to planner
                senses.append(TaskRequest(**content))

            elif content['msg_type'] == SimulationMessageTypes.PLANNER_UPDATE.value:
                # save as senses to forward to planner
                senses.append(PlannerUpdate(**content))

        return senses

    async def think(self, senses: list) -> list:
        # # send all sensed messages to planner
        # self.log(f'sending {len(senses)} senses to planning module...')
        # for sense in senses:
        #     sense : SimulationMessage
        #     sense.src = self.get_element_name()
        #     sense.dst = self.get_element_name()
        #     await self.send_internal_message(sense)

        # # wait for planner to send list of tasks to perform
        # self.log(f'senses sent! waiting on plan to perform...')
        # actions = []
        # _, _, content = await self.internal_inbox.get()
        # self.log(f"plan received from planner module!")
        
        # if content['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
        #     msg = AgentActionMessage(**content)
        #     self.log(f"received an action of type {msg.action['action_type']}")
        #     actions.append(msg.action)
        
        # TEMPORARY: Fixed plan execution
        ## Remove completed or aborted tasks from plan
        actions = []
        removed = []
        for action_dict in self.plan:
            action_dict : dict
            action = AgentAction(**action_dict)
            t_curr = self.get_current_time()

            if action.t_end < t_curr and action.id not in self.state.tasks_performed:
                # remove from plan if end time has passed and action was not performed 
                removed.append(action_dict)

            if action.id in self.state.tasks_performed:
                # remove from plan if action was successfully performed 
                removed.append(action_dict)

            elif action.t_start <= t_curr <= action.t_end:
                # perform action if in between the assigned time
                actions.append(action_dict)
        
        for action in removed:
            self.plan.remove(action)

        if len(actions) == 0:
            t_idle = 1e6
            for action_dict in self.plan:
                action_dict : dict
                action = AgentAction(**action_dict)
                
                t_idle = action.t_start if action.t_start < t_idle else t_idle

            action = IdleAction(self.get_current_time(), t_idle)
            actions.append(action.to_dict())

        # self.log(f'received {len(actions)} actions to perform.')
        return actions

    async def do(self, actions: list) -> dict:
        # only do one action at a time and discard the rest
        statuses = []

        # do fist action on the list
        self.log(f'performing {len(actions)} actions')
        
        for action_dict in actions:
            action_dict : dict
            action = AgentAction(**action_dict)

            if self.get_current_time() < action.t_start:
                self.log(f"action of type {action_dict['action_type']} has NOT started yet. waiting for start time...", level=logging.INFO)
                statuses.append((action, AgentAction.PENDING))
                
            elif action.t_end < self.get_current_time():
                self.log(f"action of type {action_dict['action_type']} has already occureed. could not perform task before...", level=logging.INFO)
                statuses.append((action, AgentAction.ABORTED))
                
            else:
                self.log(f"performing action of type {action_dict['action_type']}...", level=logging.INFO)    
                if action_dict['action_type'] == ActionTypes.PEER_MSG.value:
                    # unpack action
                    action = PeerMessageAction(**action_dict)

                    # perform action
                    self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                    await self.send_peer_message(action.msg)
                    
                    # update action completion status
                    action.status = AgentAction.COMPLETED
                    
                elif action_dict['action_type'] == ActionTypes.BROADCAST_MSG.value:
                    # unpack action
                    action = BroadcastMessageAction(**action_dict)

                    # perform action
                    self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                    await self.send_peer_broadcast(action.msg)
                    
                    # update action completion status
                    action.status = AgentAction.COMPLETED
                
                elif action_dict['action_type'] == ActionTypes.IDLE.value:
                    # unpack action 
                    action = IdleAction(**action_dict)

                    # perform action
                    self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                    delay = action.t_end - self.get_current_time()
                    await self.sim_wait(delay)

                    # update action completion status
                    if self.get_current_time() >= action.t_end:
                        action.status = AgentAction.COMPLETED
                    else:
                        action.status = AgentAction.PENDING

                elif action_dict['action_type'] == ActionTypes.MOVE.value:
                    # unpack action 
                    action = MoveAction(**action_dict)

                    # perform action
                    ## calculate new direction 
                    dx = action.pos[0] - self.state.pos[0]
                    dy = action.pos[1] - self.state.pos[1]

                    norm = math.sqrt(dx**2 + dy**2)

                    if isinstance(self._clock_config, FixedTimesStepClockConfig):
                        eps = self.state.v_max * self._clock_config.dt
                    else:
                        eps = 1e-6

                    if norm < eps:
                        self.log('agent has reached its desired position. stopping.', level=logging.DEBUG)
                        ## stop agent 
                        new_vel = [ 0, 
                                    0]
                        self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.TRAVELING)

                        # update action completion status
                        action.status = AgentAction.COMPLETED
                    else:
                        ## change velocity towards destination
                        dx = dx / norm
                        dy = dy / norm

                        new_vel = [ dx*self.state.v_max, 
                                    dy*self.state.v_max]

                        self.log(f'agent has NOT reached its desired position. updating velocity to {new_vel}', level=logging.DEBUG)
                        self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.TRAVELING)

                        ## wait until destination is reached
                        delay = norm / self.state.v_max
                        await self.sim_wait(delay)
                        
                        # update action completion status
                        action.status = AgentAction.PENDING
                
                # elif action_dict['action_type'] == ActionTypes.MEASURE.value:
                #     # unpack action 
                #     task = MeasurementTask(**action_dict)

                #     # perform action
                #     self.state.update_state(self.get_current_time(), status=SimulationAgentState.MEASURING)

                #     ## TODO get information from environment
                #     dx = task.pos[0] - self.state.pos[0]
                #     dy = task.pos[1] - self.state.pos[1]

                #     norm = math.sqrt(dx**2 + dy**2)

                #     if isinstance(self._clock_config, FixedTimesStepClockConfig):
                #         eps = self.state.v_max * self._clock_config.dt
                #     else:
                #         eps = 1e-6

                #     if norm < eps:
                #         ### agent has reached its desired position
                #         self.state.update_state(self.get_current_time(), tasks_performed=[task], status=SimulationAgentState.IDLING)

                #         # update action completion status
                #         action.status = AgentAction.COMPLETED
                #     else:
                #         ### agent has NOT reached its desired position
                #         self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)

                #         # update action completion status
                #         action.status = AgentAction.PENDING

                else:
                    # ignore action
                    self.log(f"action of type {action_dict['action_type']} not yet supported. ignoring...", level=logging.INFO)
                    action.status = AgentAction.ABORTED  
                
                statuses.append((action, action.status))

        return statuses
        # check if action can be performed at this time
        if action.t_start <= self.get_current_time() <= action.t_end:
            self.log(f"performing action of type {action_dict['action_type']}...", level=logging.INFO)
            
            if action_dict['action_type'] == ActionTypes.PEER_MSG.value:
                # unpack action
                action = PeerMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                await self.send_peer_message(action.msg)
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                
                # update action completion status
                action.status = AgentAction.COMPLETED

            elif action_dict['action_type'] == ActionTypes.BROADCAST_MSG.value:
                # unpack action
                action = BroadcastMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                await self.send_peer_broadcast(action.msg)
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                
                # update action completion status
                action.status = AgentAction.COMPLETED

            elif action_dict['action_type'] == ActionTypes.MOVE.value:
                # unpack action 
                action = MoveAction(**action_dict)

                # perform action
                ## calculate new direction 
                dx = action.pos[0] - self.state.pos[0]
                dy = action.pos[1] - self.state.pos[1]

                norm = math.sqrt(dx**2 + dy**2)

                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    eps = self.state.v_max * self._clock_config.dt
                else:
                    eps = 1e-6

                if norm < eps:
                    self.log('agent has reached its desired position. stopping.', level=logging.DEBUG)
                    ## stop agent 
                    new_vel = [ 0, 
                                0]
                    self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.IDLING)

                    # update action completion status
                    action.status = AgentAction.COMPLETED
                else:
                    ## change velocity towards destination
                    dx = dx / norm
                    dy = dy / norm

                    new_vel = [ dx*self.state.v_max, 
                                dy*self.state.v_max]

                    self.log(f'agent has NOT reached its desired position. updating velocity to {new_vel}', level=logging.DEBUG)
                    self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.TRAVELING)

                    ## wait until destination is reached
                    await self.sim_wait(norm / self.state.v_max)
                    
                    # update action completion status
                    action.status = AgentAction.PENDING

            elif action_dict['action_type'] == ActionTypes.MEASURE.value:
                # unpack action 
                task = MeasurementTask(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MEASURING)

                ## TODO get information from environment
                dx = task.pos[0] - self.state.pos[0]
                dy = task.pos[1] - self.state.pos[1]

                norm = math.sqrt(dx**2 + dy**2)

                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    eps = self.state.v_max * self._clock_config.dt
                else:
                    eps = 1e-6

                if norm < eps:
                    ### agent has reached its desired position
                    self.state.update_state(self.get_current_time(), tasks_performed=[task], status=SimulationAgentState.IDLING)

                    # update action completion status
                    action.status = AgentAction.COMPLETED
                else:
                    ### agent has NOT reached its desired position
                    self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)

                    # update action completion status
                    action.status = AgentAction.PENDING              

            elif action_dict['action_type'] == ActionTypes.IDLE.value:
                # unpack action 
                action = IdleAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                delay = action.t_end - self.get_current_time()
                await self.sim_wait(delay)

                # update action completion status
                if self.get_current_time() >= action.t_end:
                    action.status = AgentAction.COMPLETED
                else:
                    action.status = AgentAction.PENDING

            else:
                # ignore action
                self.log(f"action of type {action_dict['action_type']} not yet supported. ignoring...", level=logging.INFO)
                action.status = AgentAction.ABORTED    
        else:
            # wait for start time 
            self.log(f"action of type {action_dict['action_type']} has NOT started yet. waiting for start time...", level=logging.INFO)
            await self.sim_wait(action.t_start - self.get_current_time())

            # update action completion status
            action.status = AgentAction.PENDING
        
        self.log(f"finished performing action of type {action_dict['action_type']}! action completion status: {action.status}", level=logging.INFO)
        statuses.append( (action, action.status) )

        # discard the remaining actions
        if len(actions) > 0:
            self.log(f"setting all other actions as PENDING...")
        for action_dict in actions:
            action_dict : dict
            action = AgentAction(**action_dict)
            action.status = AgentAction.PENDING
            statuses.append( (action, action.status) )

        self.log(f'return {len(statuses)} statuses')
        return statuses