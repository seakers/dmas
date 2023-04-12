import logging
from dmas.agents import *
from dmas.network import NetworkConfig
from zmq import asyncio as azmq

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
														zmq.SUB: []},
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

    async def get_current_time(self) -> float:
        return await super().get_current_time()

    async def setup(self) -> None:
        # nothing to set-up
        return

    async def sense(self, statuses: dict) -> list:
        poller = azmq.Poller()
        socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
        socket_agents, _ = self._external_socket_map.get(zmq.REP)
        poller.register(socket_manager, zmq.POLLIN)
        poller.register(socket_agents, zmq.POLLIN)
        
        socks = dict(await poller.poll())
        
        # check if agent message is received:
        if socket_agents in socks:
            # read message from socket
            dst, src, content = await self.listen_peer_message()
            self.log(f'agent message received: {content}')

    async def think(self, senses: list) -> list:
        pass

    async def do(self, actions: list) -> dict:
        pass

    async def teardown(self) -> None:
        pass

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