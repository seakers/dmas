import copy
import math
from actions import MeasurementAction
from utils import setup_results_directory
from states import SimulationAgentState
from dmas.environments import *

from dmas.messages import *

from messages import *
from actions import MeasurementTask
from zmq import asyncio as azmq
import numpy as np

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
        self.tasks = tasks.copy()

        # setup results folder:
        self.results_path = setup_results_directory(results_path+'/'+self.get_element_name())

    async def setup(self) -> None:
        # initiate state trackers   
        self.states_tracker = {agent_name : None for agent_name in self._external_address_ledger}
        self.agent_connectivity = {agent_name : {target_name : 0 for target_name in self._external_address_ledger} for agent_name in self._external_address_ledger}

        self.agent_connectivity_history = []
        self.pulished_task_history = []
        self.measurement_history = []

        if isinstance(self._clock_config, FixedTimesStepClockConfig):
            tasks = []
            for task in self.tasks:
                task : MeasurementTask
                dt = self._clock_config.dt
                prev_t_start = task.t_start
                prev_t_end = task.t_end
                if task.t_start < np.Inf:
                    task.t_start = dt * math.floor(task.t_start/dt)
                if task.t_end < np.Inf:
                    task.t_end = dt * math.ceil(task.t_end/dt)

                if task.t_end > task.t_start:
                    task.t_end += dt
                tasks.append(task)
            self.tasks = tasks

    async def publish_tasks(self):
        self.log(f'publishing {len(self.tasks)} task requests to all agents...')
        tasks_to_pop = []
        for task in self.tasks:
            task : MeasurementTask
            if task.t_start <= self.get_current_time() <= task.t_end:
                task_req = TaskRequestMessage(self.get_element_name(), self.get_network_name(), task.to_dict())
                await self.send_peer_broadcast(task_req)
                tasks_to_pop.append(task)
            
                self.pulished_task_history.append((task, self.get_current_time()))

        for task in tasks_to_pop:
            self.tasks.remove(task)

        self.log('tasks published!')

    async def live(self) -> None:
        try:
            # create poller 
            poller = azmq.Poller()

            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            peer_socket, _ = self._external_socket_map.get(zmq.REP)

            poller.register(manager_socket, zmq.POLLIN)
            poller.register(peer_socket, zmq.POLLIN)
            
            # track agent and simulation states
            await asyncio.sleep(1e-3)

            # publish initial set of tasks
            await self.publish_tasks()

            # track agent and simulation states
            while True:
                socks = dict(await poller.poll())

                if peer_socket in socks:
                    # read message from socket
                    dst, src, content = await self.listen_peer_message()
                    
                    if content['msg_type'] == SimulationMessageTypes.MEASUREMENT.value:
                        # unpack message
                        msg = MeasurementResultsRequest(**content)
                        self.log(f'received masurement data request from {msg.src}. quering measurement results...')

                        # find/generate measurement results
                        # TODO look up requested measurement results from database/model
                        measurement_action = MeasurementAction(**msg.masurement_action)
                        agent_state= SimulationAgentState(**msg.agent_state)
                        task = MeasurementTask(**measurement_action.task)
                        measurement_data = {'agent' : msg.src, 
                                            't_img' : self.get_current_time(),
                                            'u' : self.calc_utility(agent_state, task, measurement_action.subtask_index, self.get_current_time()),
                                            'u_max' : task.s_max,
                                            'u_exp' : measurement_action.u_exp}

                        # repsond to request
                        self.log(f'measurement results obtained! responding to request')
                        resp = copy.deepcopy(msg)
                        resp.dst = resp.src
                        resp.src = self.get_element_name()
                        resp.measurement = measurement_data
                        
                        self.measurement_history.append(resp)

                        await self.respond_peer_message(resp) 

                    elif content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # unpack message
                        msg = AgentStateMessage(**content)
                        self.log(f'state message received from {msg.src}. updating state tracker...')

                        # update state tracker
                        self.states_tracker[src] = SimulationAgentState(**msg.state)
                        self.log(f'state tracker updated! sending response acknowledgement')

                        # send confirmation response
                        resp = NodeReceptionAckMessage(self.get_element_name(), src)
                        await self.respond_peer_message(resp)
                        self.log('response sent! checking if all states are in the same time...')

                        # Check if all states are of the same time
                        if not self.same_state_times():
                            continue

                        # check for range and announce chances in connectivity 
                        self.log('states are all from the same time! checking agent connectivity...')
                        range_updates : list = self.check_agent_connectivity()

                        if len(range_updates) > 0:
                            self.log(f'connectivity checked. sending {len(range_updates)} connectivity updates...')
                            for range_update in range_updates:
                                range_update : AgentConnectivityUpdate
                                await self.send_peer_broadcast(range_update)
                            self.log('connectivity updates sent!')

                        if len(self.tasks) > 0:
                            await self.publish_tasks()

                        else:
                            self.log(f'connectivity checked. no connectivity updates...')

                        ok_msg = NodeReceptionAckMessage(self.get_element_name(), self.get_network_name())
                        await self.send_peer_broadcast(ok_msg)                        

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

                elif manager_socket in socks:
                    # check if manager message is received:
                    dst, src, content = await self.listen_manager_broadcast()

                    if (dst in self.name 
                        and SimulationElementRoles.MANAGER.value in src 
                        and content['msg_type'] == ManagerMessageTypes.SIM_END.value
                        ):
                        # sim end message received
                        self.log(f"received message of type {content['msg_type']}. ending simulation...")
                        # raise asyncio.CancelledError(f"received message of type {content['msg_type']}")
                        return

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

    def calc_utility(   
                        self, 
                        state : SimulationAgentState,
                        task : MeasurementTask, 
                        subtask_index : int, 
                        t_img : float
                    ) -> float:
        """
        Calculates the expected utility of performing a measurement task

        ### Arguments:
            - state (:obj:`SimulationAgentState`): agent state before performing the task
            - task (:obj:`MeasurementTask`): task to be performed 
            - subtask_index (`int`): index of subtask to be performed
            - t_img (`float`): time at which the task will be performed

        ### Retrurns:
            - utility (`float`): estimated normalized utility 
        """
        # check time constraints
        if t_img < task.t_start or task.t_end < t_img:
            return 0.0
        
        # calculate urgency factor from task
        utility = task.s_max * np.exp( - task.urgency * (t_img - task.t_start) )

        _, dependent_measurements = task.measurement_groups[subtask_index]
        k = len(dependent_measurements) + 1

        if k / len(task.measurements) == 1.0:
            alpha = 1.0
        else:
            alpha = 1.0/3.0

        return utility * alpha / k

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
            title = f"t,src"
            for src in self.agent_connectivity:
                title += f',dst:{src}'
                dsts.append(src)
            file.write(title)

            for t, agent_connectivity in self.agent_connectivity_history:  
                for src in agent_connectivity:
                    line = f'\n{t}, {src}'
                    for dst in dsts:
                        connected = agent_connectivity[src][dst]
                        line += f', {connected}'
                    file.write(line)

        # print measurements
        with open(f"{self.results_path}/measurements.csv", "w") as file:
            title = 'task_id,measurer,x_pos,y_pos,t_start,t_end,t_corr,t_img,u_max,u_exp,u\n'
            file.write(title)

            for msg in self.measurement_history:
                msg : MeasurementResultsRequest
                measurement_action = MeasurementAction(**msg.masurement_action)
                task = MeasurementTask(**measurement_action.task)
                measurement_data : dict = msg.measurement
                measurer = msg.measurement['agent']
                t_img = msg.measurement['t_img']

                line_data = [task.id.split('-')[0],
                             measurer,
                             task.pos[0],
                             task.pos[1],
                             task.t_start,
                             task.t_end,
                             task.t_corr,
                             t_img,
                             measurement_data['u_max'],
                             measurement_data['u_exp'],
                             measurement_data['u']]

                line = ""
                for i in range(len(line_data)):
                    line += str(line_data[i])
                    if i < len(line_data)-1:
                        line += ','
                    else:
                        line += '\n'

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
