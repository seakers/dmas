from dmas.environments import *

from dmas.messages import *

from messages import *
from tasks import Task

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
                task : Task
                task_req = TaskRequest(self.name, self.get_network_name(), task)
                await self.send_peer_broadcast(task_req)

            # track agent and simulation states
            poller = zmq.Poller()
            socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
            socket_agents, _ = self._external_socket_map.get(zmq.REQ)
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
            responses = dict()
            while len(responses) < len(self._external_address_ledger):
                # read message from socket
                _, src, content = await self.listen_peer_message()
                self.log(f'agent message received: {content}')
                
                if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                    # message is of type `AgentState`
                    self.log(f"received message of type {content['msg_type']}. processing message....")

                    # unpack message
                    responses[src] = AgentStateMessage(**content)

                    # send confirmation response
                    resp = NodeReceptionAckMessage(self.get_element_name(), src)

                else:
                    # message is of an unsopported type. send blank response
                    self.log(f"received message of type {content['msg_type']}. ignoring message...")
                    resp = NodeReceptionIgnoredMessage(self.get_element_name(), src)

                # respond to request
                await self.respond_peer_message(resp)
            
            return responses

        except asyncio.CancelledError as e:
            raise e

    def check_agent_distance(self) -> list:
        """
        Checks if agents are in range of each other or not 
        """
        agent_names = self._external_address_ledger.keys()
        range_updates = []
        for i in range(len(agent_names)):
            for j in range(i+1, len(agent_names)+1):
                agent_a = agent_names[i]
                agent_b = agent_names[j]

                pos_a = self.states_tracker[agent_a]
                pos_b = self.states_tracker[agent_b]

                dist = numpy.sqrt( (pos_a[0] - pos_b[0])**2 + (pos_a[1] - pos_b[1])**2 )
                                    
                range_updates.append(AgentConnectivityUpdate(agent_a, agent_b, dist <= self.comms_range))
                range_updates.append(AgentConnectivityUpdate(agent_b, agent_a, dist <= self.comms_range))

        return range_updates

    async def listen_for_manager(self):
        try:
            while True:
                # do nothing. Manager is being listened to in `live()`
                await asyncio.sleep(1e6)
                # dst, src, content = await self._receive_manager_msg(zmq.SUB)
                # self.log(f'message received: {content}', level=logging.DEBUG)

                # if (dst in self.name 
                #     and SimulationElementRoles.MANAGER.value in src 
                #     and content['msg_type'] != ManagerMessageTypes.SIM_END.value):
                    
                #     self.log('simulation end message received! ending simulation...')
                #     break
                # else:
                #     self.manager_broadcast_queue

        except asyncio.CancelledError:
            self.log(f'`listen_for_manager()` interrupted.')
            return
        except Exception as e:
            self.log(f'`listen_for_manager()` failed. {e}')
            raise e

    async def teardown(self) -> None:
        # nothing to tear-down
        return

    async def sim_wait(self, delay: float) -> None:
        try:
            tf = self.t + delay
            while tf > self.t:
                # listen for manager's toc messages
                _, _, msg_dict = await self.listen_manager_broadcast()
                msg_dict : dict
                msg_type = msg_dict.get('msg_type', None)

                # check if message is of the desired type
                if msg_type != SimulationMessageTypes.TOC.value:
                    continue
                
                # update time
                msg = TocMessage(**msg_type)
                self.t = msg.t
                
        except asyncio.CancelledError:
            return

if __name__ == '__main__':
    port = 5555
    network_name = 'TEST_NETWORK'
    manager_network_config = NetworkConfig( network_name,
											manager_address_map = {
																	zmq.REP: [f'tcp://*:{port}'],
																	zmq.PUB: [f'tcp://*:{port+1}'],
																	zmq.PUSH: [f'tcp://localhost:{port+2}']})
			
    env_network_config = NetworkConfig( network_name,
											manager_address_map = {
													zmq.REQ: [f'tcp://localhost:{port}'],
													zmq.SUB: [f'tcp://localhost:{port+1}'],
													zmq.PUSH: [f'tcp://localhost:{port+2}']},
											external_address_map = {
													zmq.REP: [f'tcp://*:{port+3}'],
													zmq.PUB: [f'tcp://*:{port+4}']
											})

    env = SimulationEnvironment(env_network_config,
                                manager_network_config)