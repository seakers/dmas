import copy
import math
from typing import Any, Callable
import numpy as np
from zmq import asyncio as azmq

from pandas import DataFrame
from nodes.science.reqs import MeasurementRequest
from nodes.orbitdata import OrbitData
from nodes.states import GroundStationAgentState, UAVAgentState, SatelliteAgentState
from nodes.actions import MeasurementAction
from nodes.agent import SimulationAgentState
from messages import *
from utils import setup_results_directory

from dmas.environments import *
from dmas.messages import *


class SimulationEnvironment(EnvironmentNode):
    """
    ## Simulation Environment

    Environment in charge of creating task requests and notifying agents of their exiance
    Tracks the current state of the agents and checks if they are in communication range 
    of eachother.
    
    """
    SPACECRAFT = 'SPACECRAFT'
    UAV = 'UAV'
    GROUND_STATION = 'GROUND_STATION'

    def __init__(self, 
                scenario_path : dict,
                results_path : str, 
                env_network_config: NetworkConfig, 
                manager_network_config: NetworkConfig, 
                utility_func : Callable[[], Any], 
                level: int = logging.INFO, 
                logger: logging.Logger = None) -> None:
        super().__init__(env_network_config, manager_network_config, [], level, logger)

        # setup results folder:
        self.results_path = setup_results_directory(results_path+'/'+ self.get_element_name().swapcase())

        # load observation data
        self.orbitdata = OrbitData.from_directory(scenario_path)

        # load agent names and types
        self.agents = {}
        agent_names = []
        with open(scenario_path + 'MissionSpecs.json', 'r') as scenario_specs:
            scenario_dict : dict = json.load(scenario_specs)
            
            # load satellite names
            sat_names = []
            sat_list : dict = scenario_dict.get('spacecraft', None)
            if sat_list:
                for sat in sat_list:
                    sat : dict
                    sat_name = sat.get('name')
                    sat_names.append(sat_name)
                    agent_names.append(sat_name)
            self.agents[self.SPACECRAFT] = sat_names

            # load uav names
            uav_names = []
            uav_list : dict = scenario_dict.get('uav', None)
            if uav_list:
                for uav in uav_list:
                    uav : dict
                    uav_name = uav.get('name')
                    uav_names.append(uav_name)
                    agent_names.append(uav_name)
            self.agents[self.UAV] = uav_names

            # load GS agent names
            gs_names = []
            gs_list : dict = scenario_dict.get('groundStation', None)
            if gs_list:
                for gs in gs_list:
                    gs : dict
                    gs_name = gs.get('name')
                    gs_names.append(gs_name)
                    agent_names.append(gs_name)
            self.agents[self.GROUND_STATION] = gs_names

            # load connectivity settings
            scenario_dict : dict = scenario_dict.get('scenario', None)
            connectivity = scenario_dict.get('connectivity', None) if scenario_dict else None
            self.connectivity = connectivity == 'FULL'

        # initialize parameters
        self.utility_func = utility_func
        self.measurement_history = []
        self.agent_connectivity = {}
        for src in agent_names:
            for target in agent_names:
                if src not in self.agent_connectivity:
                    self.agent_connectivity[src] = {}    
                
                self.agent_connectivity[src][target] = -1

        self.measurement_reqs = {}

    async def setup(self) -> None:
        # nothing to set up
        return

    async def live(self) -> None:
        try:
            # create port poller 
            poller = azmq.Poller()

            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            agent_socket, _ = self._external_socket_map.get(zmq.REP)

            poller.register(manager_socket, zmq.POLLIN)
            poller.register(agent_socket, zmq.POLLIN)
            
            # track agent and simulation states
            while True:
                socks = dict(await poller.poll())

                if agent_socket in socks:
                    # read message from agents
                    dst, src, content = await self.listen_peer_message()
                    
                    if content['msg_type'] == SimulationMessageTypes.MEASUREMENT.value:
                        # unpack message
                        msg = MeasurementResultsRequestMessage(**content)
                        self.log(f'received masurement data request from {msg.src}. quering measurement results...')

                        # find/generate measurement results
                        measurement_action = MeasurementAction(**msg.measurement_action)
                        agent_state = SimulationAgentState.from_dict(msg.agent_state)
                        measurement_req = MeasurementRequest.from_dict(measurement_action.measurement_req)
                        measurement_data = self.query_measurement_date(agent_state, measurement_req, measurement_action)

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

                        # initiate response
                        resp_msgs = []

                        # check current state
                        updated_state = None
                        if src in self.agents[self.SPACECRAFT]:
                            # look up orbitdata
                            current_state = SatelliteAgentState(**msg.state)
                            data : OrbitData = self.orbitdata[src]
                            pos, vel, eclipse = data.get_orbit_state(current_state.t)

                            # update state
                            updated_state = current_state
                            updated_state.pos = pos
                            updated_state.vel = vel
                            updated_state.eclipse = int(eclipse)

                        elif src in self.agents[self.UAV]:
                            # Do NOT update
                            updated_state = UAVAgentState(**msg.state)

                        elif src in self.agents[self.GROUND_STATION]:
                            # Do NOT update state
                            updated_state = GroundStationAgentState(**msg.state)
                        
                        updated_state_msg = AgentStateMessage(self.get_element_name(), src, updated_state.to_dict())
                        resp_msgs.append(updated_state_msg.to_dict())

                        # check connectivity status
                        for target_type in self.agents:
                            for target in self.agents[target_type]:
                                if target == src:
                                    continue
                                
                                connected = self.check_agent_connectivity(src, target, target_type)
                                
                                if connected == 0 and self.agent_connectivity[src][target] == -1:
                                    self.agent_connectivity[src][target] = connected
                                    continue

                                if self.agent_connectivity[src][target] != connected:
                                    # only announce if changes to connectivity have been made
                                    connectivity_update = AgentConnectivityUpdate(src, target, connected)
                                    resp_msgs.append(connectivity_update.to_dict())
                                    self.agent_connectivity[src][target] = connected

                        # package response
                        resp_msg = BusMessage(self.get_element_name(), src, resp_msgs)

                        # send response
                        await self.respond_peer_message(resp_msg)

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
            self.log(f'`live()` interrupted. {e}', level=logging.DEBUG)
            return

        except Exception as e:
            self.log(f'`live()` failed. {e}', level=logging.ERROR)
            raise e

    def check_agent_connectivity(self, src : str, target : str, target_type : str) -> bool:
        """
        Checks if an agent is in communication range with another agent

        #### Arguments:
            - src (`str`): name of agent starting the connection
            - target (`str`): name of agent receving the connection
            - target_type (`str`): type of agent receving the connection

        #### Returns:
            - connected (`int`): binary value representing if the `src` and `target` are connected
        """
        if self.connectivity:
            return True

        connected = False
        if target_type == self.SPACECRAFT:
            if src in self.agents[self.SPACECRAFT]:
                # check orbit data
                src_data : OrbitData = self.orbitdata[src]
                connected = src_data.is_accessing_agent(target, self.get_current_time())
                
            elif src in self.agents[self.UAV]:
                # check orbit data with nearest GS
                target_data : OrbitData = self.orbitdata[target]
                connected = target_data.is_accessing_ground_station(target, self.get_current_time())
            
            elif src in self.agents[self.GROUND_STATION]:
                # check orbit data
                target_data : OrbitData = self.orbitdata[target]
                connected = target_data.is_accessing_ground_station(target, self.get_current_time())
        
        elif target_type == self.UAV:
            if src in self.agents[self.SPACECRAFT]:
                # check orbit data with nearest GS
                src_data : OrbitData = self.orbitdata[src]
                connected = src_data.is_accessing_ground_station(target, self.get_current_time())

            elif src in self.agents[self.UAV]:
                # always connected
                connected = True

            elif src in self.agents[self.GROUND_STATION]:
                # always connected
                connected = True
        
        elif target_type == self.GROUND_STATION:
            if src in self.agents[self.SPACECRAFT]:
                # check orbit data
                src_data : OrbitData = self.orbitdata[src]
                connected = src_data.is_accessing_ground_station(target, self.get_current_time())

            elif src in self.agents[self.UAV]:
                # always connected
                connected = True

            elif src in self.agents[self.GROUND_STATION]:
                # always connected
                connected = True

        return int(connected)

    def query_measurement_date( self, 
                                agent_state : SimulationAgentState, 
                                measurement_req : MeasurementRequest, 
                                measurement_action : MeasurementAction
                                ) -> dict:
        """
        Queries internal models or data and returns observation information being sensed by the agent
        """
        if measurement_req.id not in self.measurement_reqs:
            self.measurement_reqs[measurement_req.id] = measurement_req

        # TODO look up requested measurement results from database/model
        params = {"state" : agent_state, "req" : measurement_req, "subtask_index" : measurement_action.subtask_index, "t_img" : self.get_current_time()}
        return  {   't_img' : self.get_current_time(),
                    'u' : self.utility_func(**params),
                    'u_max' : measurement_req.s_max,
                    'u_exp' : measurement_action.u_exp}

    async def teardown(self) -> None:
        # print final time
        self.log(f'Environment shutdown with internal clock of {self.get_current_time()}[s]', level=logging.WARNING)
        
        # print received measurements
        headers = ['req_id','measurer','measurement','pos','t_start','t_end','t_corr','t_img','u_max','u_exp','u']
        data = []
        for msg in self.measurement_history:
            msg : MeasurementResultsRequestMessage
            measurement_action = MeasurementAction(**msg.measurement_action)
            req : MeasurementRequest = MeasurementRequest.from_dict(measurement_action.measurement_req)
            measurement_data : dict = msg.measurement
            measurer = msg.dst
            t_img = msg.measurement['t_img']           

            line_data = [req.id.split('-')[0],
                            measurer,
                            req.measurements[ msg.measurement_action['subtask_index'] ],
                            msg.measurement_action["measurement_req"]["pos"],
                            req.t_start,
                            req.t_end,
                            req.t_corr,
                            t_img,
                            measurement_data['u_max'],
                            measurement_data['u_exp'],
                            measurement_data['u']]
            data.append(line_data)

        measurements_df = DataFrame(data, columns=headers)
        self.log(f"MEASUREMENTS RECEIVED:\n{str(measurements_df)}\n", level=logging.WARNING)
        measurements_df.to_csv(f"{self.results_path}/measurements.csv", index=False)

        # calculate utility achieved by measurements
        utility_total = 0.0
        max_utility = 0.0
        n_coobservations = 0
        n_obervations_max = 0

        co_observations = []

        for req_id in self.measurement_reqs:
            req_id_short = req_id.split('-')[0]
            req_measurements = measurements_df \
                                .query('@req_id_short == `req_id`')
            
            req = self.measurement_reqs[req_id]
            req_utility = 0
            for _, row_i in req_measurements.iterrows():
                t_img_i = row_i['t_img']
                measurement_i = row_i['measurement']
                correlated_measurements = []

                for _, row_j in req_measurements.iterrows():
                    measurement_j = row_j['measurement']
                    t_img_j = row_j['t_img']

                    if measurement_i == measurement_j:
                        continue

                    if abs(t_img_i - t_img_j) <= req.t_corr:
                        correlated_measurements.append( measurement_j )

                subtask_index = None
                while subtask_index == None:
                    for main_measurement, dependent_measurements in req.measurement_groups:
                        if (main_measurement == measurement_i 
                            and len(np.setdiff1d(correlated_measurements, dependent_measurements)) == 0):
                            subtask_index = req.measurement_groups.index((main_measurement, dependent_measurements))
                            break
                    
                    if subtask_index == None:
                        correlated_measurements == []

                if len(correlated_measurements) > 0:
                    co_observation : list = copy.copy(dependent_measurements)
                    co_observation.append(main_measurement)
                    co_observation.append(req_id)
                    co_observation = set(co_observation) 

                    if co_observation not in co_observations:
                        co_observations.append(co_observation)
                                
                k = len(dependent_measurements) + 1
                if k / len(req.measurements) == 1.0:
                    alpha = 1.0
                else:
                    alpha = 1.0/3.0

                params = {
                            "req" : req, 
                            "subtask_index" : subtask_index,
                            "t_img" : t_img_i
                        }
                req_utility += self.utility_func(**params) * alpha 
            
            utility_total += req_utility
            max_utility += req.s_max
            n_obervations_max += len(req.measurements)


        headers = ['stat_name', 'val']
        data = [
                    ['t_start', self._clock_config.start_date], 
                    ['t_end', self._clock_config.end_date], 
                    ['n_reqs', len(self.measurement_reqs)],
                    ['n_obs_max', n_obervations_max],
                    ['n_obs', len(self.measurement_history)],
                    ['n_obs_co', len(co_observations)],
                    ['u_max', max_utility], 
                    ['u', utility_total],
                    ['u_norm', utility_total/max_utility]
                ]
        measurements_df = DataFrame(data, columns=headers)
        self.log(f"\nSIMULATION RESULTS SUMMARY:\n{str(measurements_df)}\n", level=logging.WARNING)
        measurements_df.to_csv(f"{self.results_path}/../summary.csv", index=False)

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
