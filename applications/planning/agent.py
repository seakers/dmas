import logging
import math
from planners.acbba import ACBBAPlannerModule
from planners.fixed import FixedPlannerModule
from planners.planners import *
from utils import setup_results_directory
from tasks import *
from dmas.agents import *
from dmas.network import NetworkConfig

from messages import *
from states import *

class SimulationAgent(Agent):
    def __init__(   self, 
                    results_path : str, 
                    network_name : str,
                    manager_port : int,
                    id : int,
                    manager_network_config: NetworkConfig, 
                    planner_type: PlannerTypes,
                    instruments: list,
                    initial_state: SimulationAgentState, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None) -> None:
        
        # generate network config 
        agent_network_config = NetworkConfig( 	network_name,
												manager_address_map = {
														zmq.REQ: [f'tcp://localhost:{manager_port}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+1}'],
														zmq.PUB: [f'tcp://localhost:{manager_port+2}'],
                                                        zmq.PUSH: [f'tcp://localhost:{manager_port+3}']},
												external_address_map = {
														zmq.REQ: [],
														zmq.SUB: [f'tcp://localhost:{manager_port+5}'],
														zmq.PUB: [f'tcp://*:{manager_port+6 + 4*id}']},
                                                internal_address_map = {
														zmq.REP: [f'tcp://*:{manager_port+6 + 4*id + 1}'],
														zmq.PUB: [f'tcp://*:{manager_port+6 + 4*id + 2}'],
														zmq.SUB: [f'tcp://localhost:{manager_port+6 + 4*id + 3}']
											})
        
        if planner_type is PlannerTypes.ACBBA:
            planning_module = ACBBAPlannerModule(  results_path,
                                                    manager_port,
                                                    id,
                                                    agent_network_config,
                                                    l_bundle=3,
                                                    level=level,
                                                    logger=logger)
        elif planner_type is PlannerTypes.FIXED:
            planning_module = FixedPlannerModule(results_path,
                                                 manager_port,
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
                        [planning_module], 
                        level=level, 
                        logger=logger)

        if not isinstance(instruments, list):
            raise AttributeError(f'`instruments` must be of type `list`; is of type {type(instruments)}')

        self.id = id
        self.instruments : list = instruments.copy()
        
        # TODO Implement a way to not reattempt a task from the planner that keeps failing in its execution
        self.last_action_performed : AgentAction = None
        self.last_action_attempts = 0
        self.max_action_attempts = 10

        # setup results folder:
        self.results_path = setup_results_directory(results_path+'/'+self.get_element_name())

    async def setup(self) -> None:
        return
    
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
                completed.append(action.id)

        # update state
        self.state.update_state(self.get_current_time(), 
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
        while True:
            # wait for environment messages
            _, _, msg_dict = await self.environment_inbox.get()

            if msg_dict['msg_type'] == SimulationMessageTypes.CONNECTIVITY_UPDATE.value:
                # update connectivity
                connectivity_msg = AgentConnectivityUpdate(**msg_dict)
                if connectivity_msg.connected == 1:
                    self.subscribe_to_broadcasts(connectivity_msg.target)
                else:
                    self.unsubscribe_to_broadcasts(connectivity_msg.target)
                senses.append(connectivity_msg)

            elif msg_dict['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                # save as senses to forward to planner
                task_msg = TaskRequest(**msg_dict)
                task_msg.dst = self.get_element_name()
                senses.append(task_msg)

            elif msg_dict['msg_type'] == NodeMessageTypes.RECEPTION_ACK.value:
                # no relevant information was sent by the environment
                break
        
        # handle peer broadcasts
        while not self.external_inbox.empty():
            _, _, content = await self.external_inbox.get()

            if content['msg_type'] == SimulationMessageTypes.BUS.value:
                msg = BusMessage(**content)
                msg_dicts = msg.contents
            else:
                msg_dicts = [content]

            for msg_dict in msg_dicts:
                # save as senses to forward to planner
                if msg_dict['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                    senses.append(AgentStateMessage(**msg_dict))

                elif msg_dict['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                    senses.append(TaskRequest(**msg_dict))

                elif msg_dict['msg_type'] == SimulationMessageTypes.PLANNER_RESULTS.value:
                    senses.append(PlannerResultsMessage(**msg_dict))

                elif msg_dict['msg_type'] == SimulationMessageTypes.TASK_BID.value:
                    senses.append(TaskBidMessage(**msg_dict))

        return senses

    async def think(self, senses: list) -> list:
        # send all sensed messages to planner
        self.log(f'sending {len(senses)} senses to planning module...')
        senses_dict = []
        state_dict = None
        for sense in senses:
            sense : SimulationMessage
            if isinstance(sense, AgentStateMessage) and sense.src == self.get_element_name():
                state_dict = sense.to_dict()
            else:
                senses_dict.append(sense.to_dict())

        senses_msg = SensesMessage(self.get_element_name(), self.get_element_name(), state_dict, senses_dict)
        await self.send_internal_message(senses_msg)

        # wait for planner to send list of tasks to perform
        self.log(f'senses sent! waiting on response from planner module...')
        actions = []
        
        while len(actions) == 0:
            _, _, content = await self.internal_inbox.get()
            
            if content['msg_type'] == SimulationMessageTypes.PLAN.value:
                msg = PlanMessage(**content)
                for action_dict in msg.plan:
                    self.log(f"received an action of type {action_dict['action_type']}")
                    actions.append(action_dict)  
        
        self.log(f"plan of {len(actions)} actions received from planner module!")
        return actions

    async def do(self, actions: list) -> dict:
        statuses = []
        self.log(f'performing {len(actions)} actions')
        
        for action_dict in actions:
            action_dict : dict
            action = AgentAction(**action_dict)
            t_0 = time.perf_counter()

            if self.get_current_time() < action.t_start:
                self.log(f"action of type {action_dict['action_type']} has NOT started yet. waiting for start time...", level=logging.INFO)
                action.status = AgentAction.PENDING
                statuses.append((action, action.status))
                continue
            
            if action.t_end < self.get_current_time():
                self.log(f"action of type {action_dict['action_type']} has already occureed. could not perform task before...", level=logging.INFO)
                action.status = AgentAction.ABORTED
                statuses.append((action, action.status))
                continue

            self.log(f"performing action of type {action_dict['action_type']}...", level=logging.INFO)    
            if action_dict['action_type'] == ActionTypes.PEER_MSG.value:
                # unpack action
                action = PeerMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                await self.send_peer_message(action.msg)
                
                # update action completion status
                action.status = AgentAction.COMPLETED
            
            elif action_dict['action_type'] == ActionTypes.BROADCAST_STATE.value:
                # unpack action
                action = BroadcastStateAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                msg = AgentStateMessage(self.get_element_name(), self.get_network_name(), self.state.to_dict())
                await self.send_peer_broadcast(msg)
                
                # update action completion status
                action.status = AgentAction.COMPLETED
                
            elif action_dict['action_type'] == ActionTypes.BROADCAST_MSG.value:
                # unpack action
                action = BroadcastMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                
                if action.msg['msg_type'] == SimulationMessageTypes.TASK_BID.value:

                    msg_out = TaskBidMessage(**action.msg)
                    msg_out.dst = self.get_network_name()
                    await self.send_peer_broadcast(msg_out)

                    # update action completion status
                    action.status = AgentAction.COMPLETED
                    
                elif action.msg['msg_type'] == SimulationMessageTypes.BUS.value:

                    msg_out = BusMessage(**action.msg)
                    msg_out.dst = self.get_network_name()
                    await self.send_peer_broadcast(msg_out)

                    # update action completion status
                    action.status = AgentAction.COMPLETED

                else:
                    # message type not supported
                    action.status = AgentAction.ABORTED
            
            elif action_dict['action_type'] == ActionTypes.IDLE.value:
                # unpack action 
                action = IdleAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                delay = action.t_end - self.get_current_time()
                
                try:
                    await self.sim_wait(delay)
                except asyncio.CancelledError:
                    return

                # update action completion status
                if self.get_current_time() >= action.t_end:
                    action.status = AgentAction.COMPLETED
                else:
                    action.status = AgentAction.PENDING

            elif action_dict['action_type'] == ActionTypes.MOVE.value:
                # unpack action 
                action = MoveAction(**action_dict)

                # perform action
                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    is_at_taget = self.state.is_goal_state(action.pos, self._clock_config.dt)
                else:
                    is_at_taget = self.state.is_goal_state(action.pos)

                if is_at_taget:
                    self.log('agent has reached its desired position. stopping.', level=logging.DEBUG)
                    ## stop agent 
                    self.state.update_state(self.get_current_time(), vel = [0,0], status=SimulationAgentState.TRAVELING)

                    # update action completion status
                    action.status = AgentAction.COMPLETED
                else:
                    ## calculate new direction 
                    dx = action.pos[0] - self.state.pos[0]
                    dy = action.pos[1] - self.state.pos[1]
                    norm = math.sqrt(dx**2 + dy**2)     
                    dx = dx / norm
                    dy = dy / norm

                    ## change velocity towards destination
                    new_vel = [ dx*self.state.v_max, 
                                dy*self.state.v_max]

                    self.log(f'agent has NOT reached its desired position. updating velocity to {new_vel}', level=logging.DEBUG)
                    self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.TRAVELING)

                    ## wait until destination is reached
                    delay = norm / self.state.v_max
                    try:
                        await self.sim_wait(delay)
                    except asyncio.CancelledError:
                        return

                    # ## Check if destination has been reached
                    # self.state.update_state(self.get_current_time(), status=SimulationAgentState.TRAVELING)

                    # ## calculate new direction 
                    # if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    #     is_at_taget = self.state.is_goal_state(action.pos, action.t_end, self._clock_config.dt)
                    # else:
                    #     is_at_taget = self.state.is_goal_state(action.pos, action.t_end)

                    # # update action completion status
                    # if is_at_taget:
                    #     action.status = AgentAction.COMPLETED
                    # else:
                    #     action.status = AgentAction.PENDING

                    action.status = AgentAction.PENDING
            
            elif action_dict['action_type'] == ActionTypes.MEASURE.value:
                # unpack action 
                task = MeasurementTask(**action_dict)

                # perform action
                self.state : SimulationAgentState
                dx = task.pos[0] - self.state.pos[0]
                dy = task.pos[1] - self.state.pos[1]

                norm = math.sqrt(dx**2 + dy**2)

                ## Check if point has been reached
                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    eps = self.state.v_max * self._clock_config.dt / 2.0
                else:
                    eps = 1e-6

                if norm < eps:
                    ### agent has reached its desired position
                    # perform measurement
                    self.state.update_state(self.get_current_time(), status=SimulationAgentState.MEASURING)
                    
                    try:
                        # send a measurement data request to the environment
                        measurement = MeasurementResultsRequest(self.get_element_name(),
                                                        SimulationElementRoles.ENVIRONMENT.value, 
                                                        task.to_dict()
                                                        )

                        dst, src, measurement_dict = await self.send_peer_message(measurement)

                        # add measurement to environment inbox to be processed during `sensing()`
                        await self.environment_inbox.put((dst, src, measurement_dict))

                        # wait for the designated duration of the measurmeent 
                        await self.sim_wait(task.duration)  # TODO only compensate for the time lost between queries
                        
                    except asyncio.CancelledError:
                        return

                    # update action completion status
                    action.status = AgentAction.COMPLETED

                else:
                    ### agent has NOT reached its desired position
                    # update action completion status
                    action.status = AgentAction.ABORTED

            elif action_dict['action_type'] == ActionTypes.WAIT_FOR_MSG.value:
                # unpack action 
                task = WaitForMessages(**action_dict)
                t_curr = self.get_current_time()
                self.state.update_state(t_curr, status=SimulationAgentState.LISTENING)

                if not self.external_inbox.empty():
                    action.status = AgentAction.COMPLETED
                else:
                    timeout = asyncio.create_task(self.sim_wait(task.t_end - t_curr))
                    receive_broadcast = asyncio.create_task(self.external_inbox.get())

                    done, _ = await asyncio.wait([timeout, receive_broadcast], return_when=asyncio.FIRST_COMPLETED)

                    if receive_broadcast in done:
                        # a mesasge was received before the timer ran out; cancel timer
                        try:
                            timeout.cancel()
                            await timeout
                        except asyncio.CancelledError:
                            # restore message to inbox so it can be processed during `sense()`
                            await self.external_inbox.put(receive_broadcast.result())    

                            # update action completion status
                            action.status = AgentAction.COMPLETED                
                    else:
                        # timer ran out or time advanced
                        try:
                            receive_broadcast.cancel()
                            await receive_broadcast
                        except asyncio.CancelledError:
                            # update action completion status
                            if self.external_inbox.empty():
                                action.status = AgentAction.PENDING
                            else:
                                action.status = AgentAction.COMPLETED
            else:
                # ignore action
                self.log(f"action of type {action_dict['action_type']} not yet supported. ignoring...", level=logging.INFO)
                action.status = AgentAction.ABORTED  
                
            self.log(f"finished performing action of type {action_dict['action_type']}! action completion status: {action.status}", level=logging.INFO)
            statuses.append((action, action.status))

            if (action.status in [
                                    AgentAction.COMPLETED, 
                                    AgentAction.PENDING,
                                    AgentAction.ABORTED
                                ]):
                dt = time.perf_counter() - t_0
                if action_dict['action_type'] not in self.stats:
                    self.stats[action_dict['action_type']] = []    
                self.stats[action_dict['action_type']].append(dt)

        self.log(f'returning {len(statuses)} statuses')
        return statuses

    async def teardown(self) -> None:
        # log agent capabilities
        out = f'\ninstruments: {self.instruments}'

        # log state 
        out += '\nt, pos, vel, status\n'
        for state_dict in self.state.history:
            out += f"{np.round(state_dict['t'],3)},\t[{np.round(state_dict['pos'][0],3)}, {np.round(state_dict['pos'][1],3)}], [{np.round(state_dict['vel'][0],3)}, {np.round(state_dict['vel'][1],3)}], {state_dict['status']}\n"    
        
        # log performance stats
        out += '\nROUTINE RUN-TIME STATS'
        out += '\nroutine\t\tt_avg\tt_std\tt_med\tn\n'
        n_decimals = 5
        for routine in self.stats:
            t_avg = np.mean(self.stats[routine])
            t_std = np.std(self.stats[routine])
            t_median = np.median(self.stats[routine])
            n = len(self.stats[routine])
            if len(routine) < 5:
                out += f'`{routine}`:\t\t'
            elif len(routine) < 13:
                out += f'`{routine}`:\t'
            else:
                out += f'`{routine}`:'
            out += f'{np.round(t_avg,n_decimals)}\t{np.round(t_std,n_decimals)}\t{np.round(t_median,n_decimals)}\t{n}\n'
        self.log(out, level=logging.WARNING)

        # print agent states
        with open(f"{self.results_path}/states.csv", "w") as file:
            title = 't,x_pos,y_pos,x_vel,y_vel,status'
            file.write(title)

            for state_dict in self.state.history:
                pos = state_dict['pos']
                vel = state_dict['vel']
                file.write(f"\n{state_dict['t']},{pos[0]},{pos[1]},{vel[0]},{vel[1]},{state_dict['status']}")

    async def sim_wait(self, delay: float) -> None:
        try:  
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ):
                if delay < 1e-6: 
                    ignored = None
                    return

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
                    toc_msg = None
                    confirmation = None
                    confirmation = await self._send_manager_msg(tic_req, zmq.PUB)

                    self.log(f'tic request for {tf}[s] sent! waiting on toc broadcast...')
                    dst, src, content = await self.manager_inbox.get()
                    
                    if content['msg_type'] == ManagerMessageTypes.TOC.value:
                        # update clock
                        toc_msg = TocMessage(**content)
                        await self.update_current_time(toc_msg.t)
                        self.log(f'toc received! time updated to: {self.get_current_time()}[s]')
                    else:
                        # ignore message
                        self.log(f'some other manager message was received. ignoring...')
                        ignored.append((dst, src, content))

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
        
        except asyncio.CancelledError as e:
            # if still waiting on  cancel request
            if confirmation is not None and toc_msg is None:
                tic_cancel = CancelTicRequest(self.get_element_name(), t0, tf)
                await self._send_manager_msg(tic_cancel, zmq.PUB)

            raise e

        finally:
            if (
                isinstance(self._clock_config, FixedTimesStepClockConfig) 
                or isinstance(self._clock_config, EventDrivenClockConfig)
                ) and ignored is not None:

                # forward all ignored messages as manager messages
                for dst, src, content in ignored:
                    await self.manager_inbox.put((dst,src,content))
