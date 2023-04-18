import logging
import math
from dmas.agents import *
from dmas.network import NetworkConfig

from messages import *
from states import *
from planners import *


class ActionTypes(Enum):
    PEER_MSG = 'PEER_MSG'
    BROADCAST_MSG = 'BROADCAST_MSG'
    MOVE = 'MOVE'
    MEASURE = 'MEASURE'
    IDLE = 'IDLE'

class PeerMessageAction(AgentAction):
    """
    ## Peer-Message Action 

    Instructs an agent to send a message directly to a peer
    """
    def __init__(self, 
                msg : SimulationMessage,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.PEER_MSG.value, t_start, t_end, status, id, **_)
        self.msg = msg

class BroadcastMessageAction(AgentAction):
    """
    ## Broadcast Message Action 

    Instructs an agent to broadcast a message to all of its peers
    """
    def __init__(self, 
                msg : SimulationMessage,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.BROADCAST_MSG.value, t_start, t_end, status, id, **_)
        self.msg = msg

class MoveAction(AgentAction):
    """
    ## Move Action

    Instructs an agent to move to a particular position
    """
    def __init__(self,
                pos : list, 
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.MOVE.value, t_start, t_end, status, id, **_)
        self.pos = pos

class MeasurementAction(AgentAction):
    """
    ## Measuremet Action

    Instructs an agent to perform a measurement
    """
    def __init__(self, 
                task : MeasurementTask,
                instruments : list,
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.MEASURE.value, t_start, t_end, status, id, **_)
        self.task = task
        self.instruments = instruments

class IdleAction(AgentAction):
    """
    ## Idle Action

    Instructs an agent to idle for a given amount of time
    """
    def __init__(self, 
                t_start : Union[float, int],
                t_end : Union[float, int], 
                status : str = 'PENDING',
                id: str = None, 
                **_) -> None:
        super().__init__(ActionTypes.IDLE.value, t_start, t_end, status, id, **_)

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
        else:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')

        super().__init__(f'AGENT_{id}', 
                        agent_network_config, 
                        manager_network_config, 
                        initial_state, 
                        [planning_module], 
                        level, 
                        logger)

    async def setup(self) -> None:
        # nothing to set up
        return

    async def sense(self, statuses: dict) -> list:
        # initiate senses array
        senses = []

        # check status of previously performed tasks
        completed = []
        for action in statuses:
            # sense and compile updated task status for planner 
            action : AgentAction
            status = statuses[action]
            msg = AgentActionMessage(   self.get_element_name(), 
                                        self.get_element_name(), 
                                        action.to_dict(),
                                        status)
            senses.append(msg)      

            # compile completed tasks for state tracking
            if status == AgentAction.COMPLETED:
                self.state : SimulationAgentState
                completed.append(action)

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

        # check if there is more than one agent in the simulation
        if len(self._external_address_ledger) > 1:
            # if so, wait for environment updates
            while True:
                # wait for environment updates
                _, _, content = await self.environment_inbox.get()

                if content['msg_type'] == SimulationMessageTypes.CONNECTIVITY_UPDATE.value:
                    # update connectivity
                    msg = AgentConnectivityUpdate(**msg)
                    if msg.connected:
                        self.subscribe_to_broadcasts(msg.target)
                    else:
                        self.unsubscribe_to_broadcasts(msg.target)

                elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                    # save as senses to forward to planner
                    senses.append(TaskRequest(**content))
                    
                # give environment time to continue sending any pending messages if any are yet to be transmitted
                await asyncio.sleep(0.01)

                if self.environment_inbox.empty():
                    # continue until no more environment messages are received
                    break        
        else:
            # else check if environment updates exist, if not skip
            while not self.environment_inbox.empty():
                # wait for environment updates
                _, _, content = await self.environment_inbox.get()

                if content['msg_type'] == SimulationMessageTypes.CONNECTIVITY_UPDATE.value:
                    # update connectivity
                    msg = AgentConnectivityUpdate(**msg)
                    if msg.connected:
                        self.subscribe_to_broadcasts(msg.target)
                    else:
                        self.unsubscribe_to_broadcasts(msg.target)

                elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                    # save as senses to forward to planner
                    senses.append(TaskRequest(**content))
                    
                # give environment time to continue sending any pending messages if any are yet to be transmitted
                await asyncio.sleep(0.01)
        
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
        # send all sensed messages to planner
        for sense in senses:
            sense : SimulationMessage
            sense.src = self.get_element_name()
            sense.dst = self.get_element_name()
            await self.send_internal_message(sense)

        # wait for planner to send list of tasks to perform
        actions = []
        while True:
            _, _, content = await self.internal_inbox.get()
            if content['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                msg = AgentActionMessage(**content)
                actions.append(msg.action)

            # give planner time to continue sending any pending messages if any are yet to be transmitted
            await asyncio.sleep(0.01)

            if self.internal_inbox.empty():
                break

        return actions

    async def do(self, actions: list) -> dict:
        # only do one action at a time and discard the rest
        statuses = {}

        # do fist action on the list
        action_msg : AgentActionMessage = actions.pop()
        action_dict = action_msg.action
        action = AgentAction(action_dict)

        # check if action can be performed at this time
        if action.t_start <= self.get_current_time() <= action.t_end:
            if action_dict['action_type'] == ActionTypes.PEER_MSG.value:
                # unpack action
                action = PeerMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                await self.send_peer_message(action.msg)
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                
                # update action completion status
                action.status = AgentAction.COMPLETED

            elif action_msg['action_type'] == ActionTypes.BROADCAST_MSG.value:
                # unpack action
                action = BroadcastMessageAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MESSAGING)
                await self.send_peer_broadcast(action.msg)
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                
                # update action completion status
                action.status = AgentAction.COMPLETED

            elif action_msg['action_type'] == ActionTypes.MOVE.value:
                # unpack action 
                action = MoveAction(**action_dict)

                # perform action
                ## calculate new direction 
                dx = action.pos[0] - self.state.pos[0]
                dy = action.pos[1] - self.state.pos[1]
                dz = action.pos[2] - self.state.pos[2]

                norm = math.sqrt(dx**2 + dy**2 + dz**2)

                if isinstance(self._clock_config, FixedTimesStepClockConfig):
                    eps = self.state.v_max * self._clock_config.dt
                else:
                    eps = 1e-6

                if norm < eps:
                    ### agent has reached its desired position
                    ## stop agent 
                    new_vel = [ 0, 
                                0, 
                                0]
                    self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.IDLING)

                    # update action completion status
                    action.status = AgentAction.COMPLETED
                else:
                    ### agent has NOT reached its desired position
                    ## change velocity towards destination
                    dx = dx / norm
                    dy = dy / norm
                    dz = dz / norm

                    new_vel = [ dx*self.state.v_max, 
                                dy*self.state.v_max, 
                                dz*self.state.v_max]

                    self.state.update_state(self.get_current_time(), vel = new_vel, status=SimulationAgentState.TRAVELING)

                    ## wait until destination is reached
                    await self.sim_wait(norm / self.state.v_max)
                    
                    # update action completion status
                    action.status = AgentAction.PENDING

            elif action_msg['action_type'] == ActionTypes.MEASURE.value:
                # unpack action 
                action = MeasurementAction(**action_dict)
                task : MeasurementTask = action.task

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.MEASURING)

                ## TODO get information from environment
                dx = task.pos[0] - self.state.pos[0]
                dy = task.pos[1] - self.state.pos[1]
                dz = task.pos[2] - self.state.pos[2]

                norm = math.sqrt(dx**2 + dy**2 + dz**2)

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

            elif action_msg['action_type'] == ActionTypes.IDLE.value:
                # unpack action 
                action = IdleAction(**action_dict)

                # perform action
                self.state.update_state(self.get_current_time(), status=SimulationAgentState.IDLING)
                await self.sim_wait(action.t_end - self.get_current_time())

                # update action completion status
                if self.get_current_time() >= action.t_end:
                    action.status = AgentAction.COMPLETED
                else:
                    action.status = AgentAction.PENDING

            else:
                # ignore action
                action.status = AgentAction.ABORTED    
        else:
            # wait for start time 
            await self.sim_wait(action.t_start - self.get_current_time())

            # update action completion status
            action.status = AgentAction.PENDING
        
        statuses[action] = action.status

        # discard the remaining actions
        for action_msg in actions:
            action = AgentAction(action_dict)
            action.status = AgentAction.PENDING
            statuses[action] = action.status

        return statuses

    async def teardown(self) -> None:
        # print state history
        out = ''
        for state_dict in self.state.history:
            out += f'{state_dict}\n'

        self.log(out)

    async def sim_wait(self, delay: float) -> None:
        try:
            if (isinstance(self._clock_config, FixedTimesStepClockConfig)
                or isinstance(self._clock_config, EventDrivenClockConfig)):
                if delay > 0:
                    # desired time not yet reached
                    t0 = self.get_current_time()
                    tf = t0 + delay
                    
                    # wait for time update                    
                    while self.get_current_time() <= t0:
                        # send tic request
                        tic_req = TicRequest(self.get_element_name(), t0, tf)
                        await self.send_manager_message(tic_req)

                        dst, src, content = await self.manager_inbox.get()
                        
                        if content['msg_type'] == ManagerMessageTypes.TOC.value:
                            # update clock
                            msg = TocMessage(**content)
                            await self.update_current_time(msg.t)

                        else:
                            # ignore message
                            self.manager_inbox.put( (dst, src, content) )


            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
                
        except asyncio.CancelledError:
            return