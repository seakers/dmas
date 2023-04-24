from utils import setup_results_directory
from states import SimulationAgentState
from dmas.environments import *

from dmas.messages import *

from messages import *
from tasks import MeasurementTask
from zmq import asyncio as azmq

class SimulationEnvironment(EnvironmentNode):
    """
    ## Simulation Environment

    Environment in charge of creating task requests and notifying agents of their exiance
    Tracks the current state of the agents and checks if they are in communication range 
    of eachother.
    
    """
    def __init__(self, 
                results_path : str, 
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
        self.tasks = tasks

        # setup results folder:
        self.results_path = setup_results_directory(results_path+'/'+self.get_element_name())

    async def setup(self) -> None:
        # initiate state trackers   
        self.states_tracker = {agent_name : None for agent_name in self._external_address_ledger}
        self.agent_connectivity = {agent_name : {target_name : 0 for target_name in self._external_address_ledger} for agent_name in self._external_address_ledger}

        self.agent_connectivity_history = []

    async def live(self) -> None:
        try:
            # broadcast task requests
            self.log(f'publishing {len(self.tasks)} task requests to all agents...')
            for task in self.tasks:
                task : MeasurementTask
                task_req = TaskRequest(self.name, self.get_network_name(), task.to_dict())
                await self.send_peer_broadcast(task_req)

            # track agent and simulation states
            poller = azmq.Poller()
            socket_manager, _ = self._manager_socket_map.get(zmq.SUB)
            socket_agents, _ = self._external_socket_map.get(zmq.REP)
            poller.register(socket_manager, zmq.POLLIN)
            poller.register(socket_agents, zmq.POLLIN)

            # listen for messages
            self.log(f'task requests broadcasted! listening to incoming messages...')
            while True:
                socks = dict(await poller.poll())
                
                # check if agent message is received:
                if socket_agents in socks:
                    # read message from socket
                    dst, src, content = await self.listen_peer_message()
                    
                    if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # message is of type `AgentState`
                        self.log(f"received message of type {content['msg_type']}. processing message....")

                        # unpack message
                        msg = AgentStateMessage(**content)
                        self.log(f'state received from {msg.src}. updating state tracker...')

                        # update state tracker
                        self.states_tracker[src] = SimulationAgentState(**msg.state)
                        self.log(f'state tracker updated! sending response acknowledgement')

                        # send confirmation response
                        resp = NodeReceptionAckMessage(self.get_element_name(), src)
                        await self.respond_peer_message(resp)
                        self.log('response sent! checking if all states are in the same time...')

                        ## Check if all states are of the same time
                        while not self.same_state_times():
                            self.log('states are at different times! waiting for more incoming state updates...')

                            # read message from socket
                            dst, src, content = await self.listen_peer_message()
                            self.log(f'agent message received: {content}')

                            if content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                                # message is of type `AgentState`
                                self.log(f"received message of type {content['msg_type']}. processing message....")

                                # unpack message
                                msg = AgentStateMessage(**content)

                                # update state tracker
                                self.states_tracker[src] = SimulationAgentState(**msg.state)

                            # send confirmation response
                            resp = NodeReceptionAckMessage(self.get_element_name(), src)
                            await self.respond_peer_message(resp)                       

                        # check for range and announce chances in connectivity 
                        self.log('states are all from the same time! checking agent connectivity...')
                        range_updates : list = self.check_agent_connectivity()

                        if len(range_updates) > 0:
                            self.log(f'connectivity checked. sending {len(range_updates)} connectivity updates...')
                            for range_update in range_updates:
                                range_update : AgentConnectivityUpdate
                                await self.send_peer_broadcast(range_update)
                        else:
                            self.log(f'connectivity checked. no connectivity updates...')
                            ok_msg = NodeReceptionAckMessage(self.get_element_name(), self.get_network_name())
                            await self.send_peer_broadcast(ok_msg)
                        self.log('connectivity updates sent!')

                        # save connectivity state to history
                        agent_connectivity = {}
                        for src in self.agent_connectivity:
                            connections = {dst : self.agent_connectivity[src][dst] for dst in self.agent_connectivity[src]}
                            agent_connectivity[src] = connections

                        self.agent_connectivity_history.append((self.get_current_time(), agent_connectivity.copy()))
                        
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

                    if (dst in self.name 
                        and SimulationElementRoles.MANAGER.value in src 
                        and content['msg_type'] == ManagerMessageTypes.SIM_END.value
                        ):
                        # sim end message received
                        self.log(f"received message of type {content['msg_type']}. ending simulation...")
                        raise asyncio.CancelledError(f"received message of type {content['msg_type']}")

                    elif content['msg_type'] == ManagerMessageTypes.TOC.value:
                        # toc message received

                        # unpack message
                        msg = TocMessage(**content)

                        # update internal clock
                        self.log(f"received message of type {content['msg_type']}. updating internal clock to {msg.t}[s]...")
                        await self.update_current_time(msg.t)

                        # wait for all agent's to send their updated states
                        self.log(f"internal clock uptated to time {self.get_current_time()}[s]!")
                    
                    else:
                        # ignore message
                        self.log(f"received message of type {content['msg_type']}. ignoring message...")
                    

        except asyncio.CancelledError:
            return

        except Exception as e:
            self.log(f'`live()` failed. {e}', level=logging.ERROR)
            raise e

    def same_state_times(self) -> bool:
        """
        Checks if all agents' states being tracked are of the same time-step
        """
        t = -1
        for agent in self.states_tracker:
            state : SimulationAgentState = self.states_tracker[agent]

            if state is None:
                if t == -1:
                    t = None
                    continue

                elif t is None:
                    continue

                elif t != None:
                    return False                    
            else:
                if t == -1:
                    t = state.t 
                    continue
                
                elif t is None:
                    return False

                if abs(t - state.t) > 1e-6:
                    return False

        return True

    def check_agent_connectivity(self) -> list:
        """
        Checks if agents are in communication range of each other
        """
        # get list of agents
        agent_names = list(self._external_address_ledger.keys())

        if len(agent_names) < 2:
            return []

        range_updates = []
        for i in range(len(agent_names)):
            agent_a = agent_names[i]

            if agent_a == self.get_element_name():
                # agents cannot re-connect to environment
                continue
            
            for j in range(i+1, len(agent_names)):
                agent_b = agent_names[j]

                if agent_b == self.get_element_name():
                    # agents cannot disconnect to environment
                    continue

                if agent_b == agent_a:
                    # agents cannot connect to themselves
                    continue
                
                # check for changes in agent connectivity based on distance and comms range
                state_a : SimulationAgentState = self.states_tracker[agent_a]
                pos_a = state_a.pos
                state_b : SimulationAgentState = self.states_tracker[agent_b]
                pos_b = state_b.pos

                dist = numpy.sqrt( (pos_a[0] - pos_b[0])**2 + (pos_a[1] - pos_b[1])**2 )
                
                connected = 1 if dist <= self.comms_range else 0

                # only notify agents if a change in connectivity has occurred
                if self.agent_connectivity[agent_a][agent_b] != connected:
                    range_updates.append(AgentConnectivityUpdate(agent_a, agent_b, connected))
                    self.agent_connectivity[agent_a][agent_b] = connected

                if self.agent_connectivity[agent_b][agent_a] != connected:
                    range_updates.append(AgentConnectivityUpdate(agent_b, agent_a, connected))
                    self.agent_connectivity[agent_b][agent_a] = connected

        return range_updates

    async def teardown(self) -> None:
        # print final time
        self.log(f'Environment shutdown with internal clock of {self.get_current_time()}[s]', level=logging.WARNING)
        
        # log connectiviy history
        out = '\nConnectivity history'

        for t, agent_connectivity in self.agent_connectivity_history:  
            connected = []
            for src in agent_connectivity:
                for dst in agent_connectivity[src]:
                    if src == dst:
                        continue
                    if (dst, src) in connected:
                        continue
                    if agent_connectivity[src][dst] == 1:
                        connected.append((src, dst))

            if len(connected) > 0:
                out += f'\nt:={t}[s]\n'
                for src, dst in connected:
                    out += f'\t{src} <-> {dst}\n'
        self.log(out, level=logging.WARNING)
        
        # print connectivity history
        with open(f"{self.results_path}/connectivity.csv", "w") as file:
            dsts = []
            title = f"t, src"
            for src in self.agent_connectivity:
                title += f', dst:{src}'
                dsts.append(src)
            file.write(title)

            for t, agent_connectivity in self.agent_connectivity_history:  
                for src in agent_connectivity:
                    line = f'\n{t}, {src}'
                    for dst in dsts:
                        connected = agent_connectivity[src][dst]
                        line += f', {connected}'
                    file.write(line)


    async def sim_wait(self, delay: float) -> None:
        try:
            if isinstance(self._clock_config, FixedTimesStepClockConfig):
                tf = self.get_current_time() + delay
                while tf > self.get_current_time():
                    # listen for manager's toc messages
                    _, _, msg_dict = await self.listen_manager_broadcast()

                    if msg_dict is None:
                        raise asyncio.CancelledError()

                    msg_dict : dict
                    msg_type = msg_dict.get('msg_type', None)

                    # check if message is of the desired type
                    if msg_type != ManagerMessageTypes.TOC.value:
                        continue
                    
                    # update time
                    msg = TocMessage(**msg_type)
                    self.update_current_time(msg.t)

            elif isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                await asyncio.sleep(delay / self._clock_config.sim_clock_freq)

            else:
                raise NotImplementedError(f'`sim_wait()` for clock of type {type(self._clock_config)} not yet supported.')
                
        except asyncio.CancelledError:
            return
