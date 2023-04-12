from dmas.environments import *

from dmas.messages import *

from messages import *
from tasks import AgentTask
from zmq import asyncio as azmq

class SimulationEnvironment(EnvironmentNode):
    """
    ## Simulation Environment

    Environment in charge of creating task requests and notifying agents of their exiance
    Tracks the current state of the agents and checks if they are in communication range 
    of eachother.
    
    """
    def __init__(self, 
                env_network_config: NetworkConfig, 
                manager_network_config: NetworkConfig, 
                x_bounds : list,
                y_bounds : list,
                comms_range : float,
                tasks : list,
                level: int = logging.INFO, 
                logger: logging.Logger = None) -> None:
        super().__init__(env_network_config, manager_network_config, [], level, logger)
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.comms_range = comms_range
        self.tasks = []
        self.t = None
        self.tasks = tasks

    async def setup(self) -> None:
        # initiate state trackers
        self.states_tracker = {agent_name : None for agent_name in self._external_address_ledger}

    async def live(self) -> None:
        try:
            # initiate internal clock 
            self.t = 0

            # broadcast task requests
            for task in self.tasks:
                task : AgentTask
                task_req = TaskRequest(self.name, self.get_network_name(), task.to_dict())
                await self.send_peer_broadcast(task_req)

            # track agent and simulation states
            poller = azmq.Poller()
            socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
            socket_agents, _ = self._external_socket_map.get(zmq.REP)
            poller.register(socket_manager, zmq.POLLIN)
            poller.register(socket_agents, zmq.POLLIN)

            # listen for messages
            while True:
                socks = dict(await poller.poll())
                
                # check if agent message is received:
                if socket_agents in socks:
                    # read message from socket
                    dst, src, content = await self.listen_peer_message()
                    self.log(f'agent message received: {content}')
                    
                    if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # message is of type `AgentState`
                        self.log(f"received message of type {content['msg_type']}. processing message....")

                        # unpack message
                        msg = AgentStateMessage(**content)

                        # update state tracker
                        self.states_tracker[src] : AgentStateMessage = msg.state

                        # send confirmation response
                        resp = NodeReceptionAckMessage(self.get_element_name(), src)

                    else:
                        # message is of an unsopported type. send blank response
                        self.log(f"received message of type {content['msg_type']}. ignoring message...")
                        resp = NodeReceptionIgnoredMessage(self.get_element_name(), src)

                    # respond to request
                    await self.respond_peer_message(resp)

                # check if manager message is received:
                if socket_manager in socks:
                    # read message from socket
                    dst, src, content = await self.listen_manager_broadcast()
                    self.log(f'manager message received: {content}')

                    if (dst in self.name 
                        and SimulationElementRoles.MANAGER.value in src 
                        and content['msg_type'] == ManagerMessageTypes.SIM_END.value):
                        # sim end message received

                        self.log(f"received message of type {content['msg_type']}. ending simulation...")
                        return

                    elif content['msg_type'] == SimulationMessageTypes.TOC.value:
                        # toc message received
                        self.log(f"received message of type {content['msg_type']}. ending simulation...")

                        # unpack message
                        msg = TocMessage(**content)

                        # update internal clock
                        self.t = msg.t

                        # wait for all agent's to send their updated states
                        state_updates = await self.wait_for_agent_updates()

                        # update state trackers
                        for state_name in state_updates:
                            self.states_tracker[state_name] = state_updates[state_name]

                        # check for range and announce chances in connectivity 
                        range_updates : list = self.check_agent_distance()
                        for range_update in range_updates:
                            range_update : AgentConnectivityUpdate
                            await self.send_peer_broadcast(range_update)
                    
                    else:
                        # ignore message
                        self.log(f"received message of type {content['msg_type']}. ignoring message...")
                    

        except asyncio.CancelledError:
            return

    async def wait_for_agent_updates(self) -> dict:
        """
        Waits for all agents to send in their state updates to the environment
        """
        try:
            updates = dict()
            while len(updates) < len(self._external_address_ledger) - 1:
                # read message from socket
                _, src, content = await self.listen_peer_message()
                self.log(f'agent message received: {content}')
                
                if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                    # message is of type `AgentState`
                    self.log(f"received message of type {content['msg_type']}. processing message....")

                    # unpack message
                    updates[src] = AgentStateMessage(**content)

                    # send confirmation response
                    resp = NodeReceptionAckMessage(self.get_element_name(), src)

                else:
                    # message is of an unsopported type. send blank response
                    self.log(f"received message of type {content['msg_type']}. ignoring message...")
                    resp = NodeReceptionIgnoredMessage(self.get_element_name(), src)

                # respond to request messages
                await self.respond_peer_message(resp)
            
            return updates

        except asyncio.CancelledError as e:
            raise e

    def check_agent_distance(self) -> list:
        """
        Checks if agents are in range of each other or not 
        """
        # get list of agents
        agent_names = list(self._external_address_ledger.keys())

        if len(agent_names) < 2:
            return []

        range_updates = []
        for i in range(len(agent_names)):
            if agent_a == self.get_element_name():
                continue
            
            for j in range(i+1, len(agent_names)+1):
                agent_a = agent_names[i]
                agent_b = agent_names[j]

                if agent_b == self.get_element_name():
                    continue

                pos_a = self.states_tracker[agent_a]
                pos_b = self.states_tracker[agent_b]

                dist = numpy.sqrt( (pos_a[0] - pos_b[0])**2 + (pos_a[1] - pos_b[1])**2 )
                                    
                range_updates.append(AgentConnectivityUpdate(agent_a, agent_b, dist <= self.comms_range))
                range_updates.append(AgentConnectivityUpdate(agent_b, agent_a, dist <= self.comms_range))

        return range_updates

    def get_current_time(self) -> float:
        if isinstance(self._clock_config, FixedTimesStepClockConfig):
            return self.t
        else:
            raise NotImplementedError(f'clock of config of type {type(self._clock_config)} not yet supported by environment.')

    async def teardown(self) -> None:
        # nothing to tear-down
        return

    async def sim_wait(self, delay: float) -> None:
        try:
            if isinstance(self._clock_config, FixedTimesStepClockConfig):
                tf = self.t + delay
                while tf > self.t:
                    # listen for manager's toc messages
                    _, _, msg_dict = await self.listen_manager_broadcast()

                    if msg_dict is None:
                        raise asyncio.CancelledError()

                    msg_dict : dict
                    msg_type = msg_dict.get('msg_type', None)

                    # check if message is of the desired type
                    if msg_type != SimulationMessageTypes.TOC.value:
                        continue
                    
                    # update time
                    msg = TocMessage(**msg_type)
                    self.t = msg.t

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
                
        except asyncio.CancelledError:
            return
