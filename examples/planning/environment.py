from datetime import timedelta
import random
from dmas.environments import *
from config import SimulationConfig
from dmas.messages import ManagerMessageTypes, SimulationMessage
from examples.planning.messages import SimulationMessageTypes, TaskRequest, TocMessage
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
                bounds : list,
                tasks : list,
                level: int = logging.INFO, 
                logger: logging.Logger = None) -> None:
        super().__init__(env_network_config, manager_network_config, [], level, logger)
        self.bounds = bounds
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
            while True:
                # listen for messages
                socks = dict(await poller.poll())
                
                # if agent message is received:
                if socket_agents in socks:
                    # unpack message
                    dst, src, content = await self.listen_peer_message()
                    # msg = AgentState

                    # update state tracker

                    # send confirmation response
                    resp : SimulationMessage
                    await self.respond_peer_message(resp)

                # if manager message is received:
                if socket_manager in socks:
                    dst, src, content = await self.listen_manager_broadcast()
                    self.log(f'message received: {content}', level=logging.DEBUG)

                    if (dst in self.name 
                        and SimulationElementRoles.MANAGER.value in src 
                        and content['msg_type'] == ManagerMessageTypes.SIM_END.value):
                        # sim end message received
                        self.log('simulation end message received! ending simulation...')
                        return

                    # if tock is received:
                    elif content['msg_type'] == SimulationMessageTypes.TOC.value:
                        # wait for all agent's to send their updated states
                        state_updates = await self.wait_for_agent_updates()

                        # update state trackers
                        for state_name in state_updates:
                            self.states_tracker[state_name] = state_updates[state_name]

                        # check for range 
                        # range_updates : list = check_ranges

                        # announce chances in connectivity 
                        pass
                    
                    else:
                        # ignore message
                        self.log('wrong message received. ignoring message...')    
                    

        except asyncio.CancelledError:
            return

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