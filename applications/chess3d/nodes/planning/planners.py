import os
import re
from typing import Any, Callable
from nodes.orbitdata import OrbitData
from nodes.states import *
from nodes.science.reqs import *
from messages import *
from dmas.modules import *
import pandas as pd

class PlannerTypes(Enum):
    FIXED = 'FIXED'
    GREEDY = 'GREEDY'
    MACCBBA = 'MACCBBA'
    MCCBBA = 'MCCBBA'

class Bid(ABC):
    """
    ## Measurement Request Bid for Planners

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - req (`dict`): measurement request being bid on
        - req_id (`str`): id of the request being bid on
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): time when this bid was last updated
    """
    NONE = 'None'
    
    def __init__(   self, 
                    req : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0.0, 
                    own_bid : Union[float, int] = 0.0, 
                    winner : str = NONE,
                    t_img : Union[float, int] = -1, 
                    t_update : Union[float, int] = 0.0
                    ) -> object:
        """
        Creates an instance of a task bid

        ### Arguments:
            - req (`dict`): measurement request being bid on
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): time when this bid was last updated
        """
        self.req = req
        self.req_id = req['id']
        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_img = t_img
        self.t_update = t_update

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`
        """
        return f'{self.req_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_img}'

    @abstractmethod
    def update(self, other_dict : dict, t : Union[float, int]) -> object:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on predifned rules.

        ### Arguments:
            - other_dict (`dict`): dictionary representing the bid being compared to
            - t (`float` or `dict`): time when this information is being updated

        ### Returns:
            - (`Bid` or `NoneType`): returns bid information if any changes were made.
        """
        pass

    @abstractmethod
    def _update_info(self,
                        other, 
                        **kwargs
                    ) -> None:
        """
        Updates all of the variable bid information

        ### Arguments:
            - other (`Bid`): equivalent bid being used to update information
        """
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.req_id}, given id: {other.task_id}).')

        other : Bid
        self.winning_bid = other.winning_bid
        self.winner = other.winner
        self.t_img = other.t_img

        if self.bidder == other.bidder:
            self.own_bid = other.own_bid

    @abstractmethod
    def reset(self, t_update) -> None:
        """
        Resets the values of this bid while keeping track of lates update time
        """
        self.winning_bid = 0
        self.winner = self.NONE
        self.t_img = -1
        self.t_update = t_update

    def _leave(self, _, **__) -> None:
        """
        Leaves bid as is (used for algorithm readibility).

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        return

    def _tie_breaker(self, bid1 : object, bid2 : object) -> object:
        """
        Tie-breaking criteria for determining which bid is GREATER in case winning bids are equal
        """
        bid1 : Bid
        bid2 : Bid

        if bid2.winner == self.NONE and bid1.winner != self.NONE:
            return bid2
        elif bid2.winner != self.NONE and bid1.winner == self.NONE:
            return bid1
        elif bid2.winner == self.NONE and bid1.winner == self.NONE:
            return bid1

        elif bid1.bidder == bid2.bidder:
            return bid1
        elif bid1.bidder < bid2.bidder:
            return bid1
        else:
            return bid2

    def __lt__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self != self._tie_breaker(self, other)

        return other.winning_bid > self.winning_bid

    def __gt__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self == self._tie_breaker(self, other)

        return other.winning_bid < self.winning_bid

    def __le__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid >= self.winning_bid

    def __ge__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid <= self.winning_bid

    def __eq__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        return abs(other.winning_bid - self.winning_bid) < 1e-3 and other.winner == self.winner

    def __ne__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
        return abs(other.winning_bid - self.winning_bid) > 1e-3 or other.winner != self.winner

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

    @abstractmethod
    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        pass

class PlanningModule(InternalModule):
    def __init__(self, 
                results_path : str, 
                parent_name : str,
                parent_network_config: NetworkConfig, 
                utility_func : Callable[[], Any],
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
                       
        addresses = parent_network_config.get_internal_addresses()        
        sub_addesses = []
        sub_address : str = addresses.get(zmq.PUB)[0]
        sub_addesses.append( sub_address.replace('*', 'localhost') )

        if len(addresses.get(zmq.SUB)) > 1:
            sub_address : str = addresses.get(zmq.SUB)[1]
            sub_addesses.append( sub_address.replace('*', 'localhost') )

        pub_address : str = addresses.get(zmq.SUB)[0]
        pub_address = pub_address.replace('localhost', '*')

        addresses = parent_network_config.get_manager_addresses()
        push_address : str = addresses.get(zmq.PUSH)[0]

        planner_network_config =  NetworkConfig(parent_name,
                                        manager_address_map = {
                                        zmq.REQ: [],
                                        zmq.SUB: sub_addesses,
                                        zmq.PUB: [pub_address],
                                        zmq.PUSH: [push_address]})

        super().__init__(f'{parent_name}-PLANNING_MODULE', 
                        planner_network_config, 
                        parent_network_config, 
                        level, 
                        logger)
        
        self.results_path = results_path
        self.parent_name = parent_name
        self.utility_func = utility_func
        self.plan = []
        self.stats = {}

        self.parent_agent_type = None
        self.orbitdata : OrbitData = None

    async def sim_wait(self, delay: float) -> None:
        return

    async def setup(self) -> None:
        # initialize internal messaging queues
        self.states_inbox = asyncio.Queue()
        self.action_status_inbox = asyncio.Queue()
        self.measurement_req_inbox = asyncio.Queue()
        self.measurement_bid_inbox = asyncio.Queue()

    async def live(self) -> None:
        """
        Performs two concurrent tasks:
        - Listener: receives messages from the parent agent and checks results
        - Bundle-builder: plans and bids according to local information
        """
        try:
            listener_task = asyncio.create_task(self.listener(), name='listener()')
            bundle_builder_task = asyncio.create_task(self.planner(), name='planner()')
            
            tasks = [listener_task, bundle_builder_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        finally:
            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                if not task.done():
                    task.cancel()
                    await task


    async def listener(self) -> None:
        """
        Listens for any incoming messages, unpacks them and classifies them into 
        internal inboxes for future processing
        """
        try:
            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                    return

                elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!", level=logging.DEBUG)

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)     

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                            # unpack message 
                            action_msg = AgentActionMessage(**sense)
                            self.log(f"received agent action of status {action_msg.status}!")
                            
                            # send to planner
                            await self.action_status_inbox.put(action_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                            # unpack message 
                            state_msg : AgentStateMessage = AgentStateMessage(**sense)
                            self.log(f"received agent state message!")
                                                        
                            # send to planner
                            await self.states_inbox.put(state_msg) 

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_REQ.value:
                            # unpack message 
                            req_msg = MeasurementRequestMessage(**sense)
                            self.log(f"received measurement request message!")
                            
                            # send to planner
                            await self.measurement_req_inbox.put(req_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            self.log(f"received measurement request message!")
                            
                            # send to planner
                            await self.measurement_bid_inbox.put(bid_msg)

                        # TODO support down-linked information processing

        except asyncio.CancelledError:
            return

    @abstractmethod
    async def planner(self) -> None:
        """
        Processes incoming messages from internal inboxes and sends a plan to the parent agent
        """
        pass

    def _load_orbit_data(self) -> OrbitData:
        """
        Loads agent orbit data from pre-computed csv files in scenario directory
        """
        if self.parent_agent_type != None:
            raise RuntimeError(f"orbit data already loaded. It can only be assigned once.")            

        scenario_name = self.results_path.split('/')[-1]
        scenario_dir = f'./scenarios/{scenario_name}/'
        data_dir = scenario_dir + '/orbitdata/'

        with open(scenario_dir + '/MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict : dict = json.load(scenario_specs)
            spacecraft_list : list = mission_dict.get('spacecraft', None)
            ground_station_list = mission_dict.get('groundStation', None)
            
            for spacecraft in spacecraft_list:
                spacecraft : dict
                name = spacecraft.get('name')
                index = spacecraft_list.index(spacecraft)
                agent_folder = "sat" + str(index) + '/'

                if name != self.get_parent_name():
                    continue

                # load eclipse data
                eclipse_file = data_dir + agent_folder + "eclipses.csv"
                eclipse_data = pd.read_csv(eclipse_file, skiprows=range(3))
                
                # load position data
                position_file = data_dir + agent_folder + "state_cartesian.csv"
                position_data = pd.read_csv(position_file, skiprows=range(4))

                # load propagation time data
                time_data =  pd.read_csv(position_file, nrows=3)
                _, epoc_type, _, epoc = time_data.at[0,time_data.axes[1][0]].split(' ')
                epoc_type = epoc_type[1 : -1]
                epoc = float(epoc)
                _, _, _, _, time_step = time_data.at[1,time_data.axes[1][0]].split(' ')
                time_step = float(time_step)

                time_data = { "epoc": epoc, 
                            "epoc type": epoc_type, 
                            "time step": time_step }

                # load inter-satellite link data
                isl_data = dict()
                for file in os.listdir(data_dir + '/comm/'):                
                    isl = re.sub(".csv", "", file)
                    sender, _, receiver = isl.split('_')

                    if 'sat' + str(index) in sender or 'sat' + str(index) in receiver:
                        isl_file = data_dir + 'comm/' + file
                        if 'sat' + str(index) in sender:
                            receiver_index = int(re.sub("[^0-9]", "", receiver))
                            receiver_name = spacecraft_list[receiver_index].get('name')
                            isl_data[receiver_name] = pd.read_csv(isl_file, skiprows=range(3))
                        else:
                            sender_index = int(re.sub("[^0-9]", "", sender))
                            sender_name = spacecraft_list[sender_index].get('name')
                            isl_data[sender_name] = pd.read_csv(isl_file, skiprows=range(3))

                # load ground station access data
                gs_access_data = pd.DataFrame(columns=['start index', 'end index', 'gndStn id', 'gndStn name','lat [deg]','lon [deg]'])
                for file in os.listdir(data_dir + agent_folder):
                    if 'gndStn' in file:
                        gndStn_access_file = data_dir + agent_folder + file
                        gndStn_access_data = pd.read_csv(gndStn_access_file, skiprows=range(3))
                        nrows, _ = gndStn_access_data.shape

                        if nrows > 0:
                            gndStn, _ = file.split('_')
                            gndStn_index = int(re.sub("[^0-9]", "", gndStn))
                            
                            gndStn_name = ground_station_list[gndStn_index].get('name')
                            gndStn_id = ground_station_list[gndStn_index].get('@id')
                            gndStn_lat = ground_station_list[gndStn_index].get('latitude')
                            gndStn_lon = ground_station_list[gndStn_index].get('longitude')

                            gndStn_name_column = [gndStn_name] * nrows
                            gndStn_id_column = [gndStn_id] * nrows
                            gndStn_lat_column = [gndStn_lat] * nrows
                            gndStn_lon_column = [gndStn_lon] * nrows

                            gndStn_access_data['gndStn name'] = gndStn_name_column
                            gndStn_access_data['gndStn id'] = gndStn_id_column
                            gndStn_access_data['lat [deg]'] = gndStn_lat_column
                            gndStn_access_data['lon [deg]'] = gndStn_lon_column

                            if len(gs_access_data) == 0:
                                gs_access_data = gndStn_access_data
                            else:
                                gs_access_data = pd.concat([gs_access_data, gndStn_access_data])

                # land coverage data metrics data
                payload = spacecraft.get('instrument', None)
                if not isinstance(payload, list):
                    payload = [payload]

                gp_access_data = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]', 'agent','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                for instrument in payload:
                    i_ins = payload.index(instrument)
                    gp_acces_by_mode = []

                    # modes = spacecraft.get('instrument', None)
                    # if not isinstance(modes, list):
                    #     modes = [0]
                    modes = [0]

                    gp_acces_by_mode = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])
                    for mode in modes:
                        i_mode = modes.index(mode)
                        gp_access_by_grid = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                        for grid in mission_dict.get('grid'):
                            i_grid = mission_dict.get('grid').index(grid)
                            metrics_file = data_dir + agent_folder + f'datametrics_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                            metrics_data = pd.read_csv(metrics_file, skiprows=range(4))
                            
                            nrows, _ = metrics_data.shape
                            grid_id_column = [i_grid] * nrows
                            metrics_data['grid index'] = grid_id_column

                            if len(gp_access_by_grid) == 0:
                                gp_access_by_grid = metrics_data
                            else:
                                gp_access_by_grid = pd.concat([gp_access_by_grid, metrics_data])

                        nrows, _ = gp_access_by_grid.shape
                        gp_access_by_grid['pnt-opt index'] = [mode] * nrows

                        if len(gp_acces_by_mode) == 0:
                            gp_acces_by_mode = gp_access_by_grid
                        else:
                            gp_acces_by_mode = pd.concat([gp_acces_by_mode, gp_access_by_grid])
                        # gp_acces_by_mode.append(gp_access_by_grid)

                    nrows, _ = gp_acces_by_mode.shape
                    gp_access_by_grid['instrument'] = [instrument] * nrows
                    # gp_access_data[ins_name] = gp_acces_by_mode

                    if len(gp_access_data) == 0:
                        gp_access_data = gp_acces_by_mode
                    else:
                        gp_access_data = pd.concat([gp_access_data, gp_acces_by_mode])
                
                nrows, _ = gp_access_data.shape
                gp_access_data['agent name'] = [spacecraft['name']] * nrows

                grid_data_compiled = []
                for grid in mission_dict.get('grid'):
                    i_grid = mission_dict.get('grid').index(grid)
                    grid_file = data_dir + f'grid{i_grid}.csv'

                    grid_data = pd.read_csv(grid_file)
                    nrows, _ = grid_data.shape
                    grid_data['GP index'] = [i for i in range(nrows)]
                    grid_data['grid index'] = [i_grid] * nrows
                    grid_data_compiled.append(grid_data)

                return OrbitData(name, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data, grid_data_compiled)

    def calc_imaging_time(self, state : SimulationAgentState, path : list, bids : dict, req : MeasurementRequest, subtask_index : int) -> float:
        """
        Computes the ideal" time when a task in the path would be performed
        ### Returns
            - t_img (`float`): earliest available imaging time
        """
        # calculate the state of the agent prior to performing the measurement request
        i = path.index((req, subtask_index))
        if i == 0:
            t_prev = state.t
            prev_state = state.copy()
        else:
            prev_req, prev_subtask_index = path[i-1]
            prev_req : MeasurementRequest; prev_subtask_index : int
            bid_prev : Bid = bids[prev_req.id][prev_subtask_index]
            t_prev : float = bid_prev.t_img + prev_req.duration

            if isinstance(state, SatelliteAgentState):
                prev_state : SatelliteAgentState = state.propagate(t_prev)
                
                prev_state.attitude = [
                                        prev_state.calc_off_nadir_agle(prev_req),
                                        0.0,
                                        0.0
                                    ]
            elif isinstance(state, UAVAgentState):
                prev_state = state.copy()
                prev_state.t = t_prev
                
                if isinstance(prev_req, GroundPointMeasurementRequest):
                    prev_state.pos = prev_req.pos
                else:
                    raise NotImplementedError
            else:
                raise NotImplementedError(f"cannot calculate imaging time for agent states of type {type(state)}")

        return self.calc_arrival_times(prev_state, req, t_prev)[0]

    def calc_arrival_times(self, state : SimulationAgentState, req : MeasurementRequest, t_prev : Union[int, float]) -> float:
        """
        Estimates the quickest arrival time from a starting position to a given final position
        """
        if isinstance(req, GroundPointMeasurementRequest):
            # compute earliest time to the task
            if isinstance(state, SatelliteAgentState):
                t_imgs = []
                lat,lon,_ = req.lat_lon_pos
                df : pd.DataFrame = self.orbitdata.get_ground_point_accesses_future(lat, lon, t_prev)

                for _, row in df.iterrows():
                    t_img = row['time index'] * self.orbitdata.time_step
                    dt = t_img - state.t
                
                    # propagate state
                    propagated_state : SatelliteAgentState = state.propagate(t_img)

                    # compute off-nadir angle
                    thf = propagated_state.calc_off_nadir_agle(req)
                    dth = thf - propagated_state.attitude[0]

                    # estimate arrival time using fixed angular rate TODO change to 
                    if dt >= dth / 1.0: # TODO change maximum angular rate 
                        t_imgs.append(t_img)
                return t_imgs

            elif isinstance(state, UAVAgentState):
                dr = np.array(req.pos) - np.array(state.pos)
                norm = np.sqrt( dr.dot(dr) )
                return [norm / state.max_speed + t_prev]

            else:
                raise NotImplementedError(f"arrival time estimation for agents of type {self.parent_agent_type} is not yet supported.")

        else:
            raise NotImplementedError(f"cannot calculate imaging time for measurement requests of type {type(req)}")       

# class ConsensusPlanner(PlannerModule):
#     """
#     # Abstract Consensus-Based Bundle Algorithm Planner
#     """
#     def __init__(
#                 self,  
#                 results_path: str,
#                 manager_port: int, 
#                 agent_id: int, 
#                 parent_network_config: NetworkConfig, 
#                 planner_type: PlannerTypes,
#                 l_bundle: int,
#                 level: int = logging.INFO, 
#                 logger: logging.Logger = None
#                 ) -> None:
#         """
#         Creates an instance of this consensus planner

#         ### Arguments:
#             - results_path (`str`): path for printing this planner's results
#             - manager_port (`int`): localhost port used by the parent agent
#             - agent_id (`int`): iddentification number for the parent agent
#             - parent_network_config (:obj:`NetworkConfig`): network config of the parent agent
#             - planner_type (:obj:`PlanerTypes`): type of consensus planner being generated
#             - l_bundle (`int`): maximum bundle size
#             - level (`int`): logging level
#             - logger (`logging.Logger`): logger being used 
#         """
#         super().__init__(   results_path,
#                             manager_port, 
#                             agent_id, 
#                             parent_network_config,
#                             planner_type, 
#                             level, 
#                             logger)

#         if not isinstance(l_bundle, int) and not isinstance(l_bundle, float):
#             raise AttributeError(f'`l_bundle` must be of type `int` or `float`; is of type `{type(l_bundle)}`')
        
#         self.l_bundle = l_bundle

#         self.t_curr = 0.0
#         self.state_curr = None
#         self.listener_results = None
#         self.bundle_builder_results = None

#     @abstractmethod
#     def path_constraint_sat(self, path : list, results : dict, t_curr : Union[float, int]) -> bool:
#         """
#         Checks if the bids of every task in the current path have all of their constraints
#         satisfied by other bids.

#         ### Returns:
#             - True if all constraints are met; False otherwise
#         """

#     @abstractmethod
#     def check_task_constraints(self, task : MeasurementTask, results : dict) -> bool:
#         """
#         Checks if the bids in the current results satisfy the constraints of a given task.

#         ### Returns:
#             - True if all constraints are met; False otherwise
#         """
#         pass

#     def get_available_tasks(self, state : SimulationAgentState, bundle : list, results : dict) -> list:
#         """
#         Checks if there are any tasks available to be performed

#         ### Returns:
#             - list containing all available and bidable tasks to be performed by the parent agent
#         """
#         available = []
#         for task_id in results:
#             bid : Bid = results[task_id]
#             task = MeasurementTask(**bid.task)

#             if self.can_bid(state, task) and task not in bundle and (bid.t_img >= state.t or bid.t_img < 0):
#                 available.append(task)

#         return available

#     @abstractmethod
#     def can_bid(self, **kwargs) -> bool:
#         """
#         Checks if an agent can perform a measurement task
#         """
#         pass

#     @abstractmethod
#     def calc_path_bid(self, state : SimulationAgentState, original_path : list, task : MeasurementTask) -> tuple:
#         """
#         Calculates the best possible bid for a given task and creates the best path to accomodate said task

#         ### Arguments:
#         - state (:obj:`SimulationAgentState`): latest known state of the agent
#         - original_path (`list`): sequence of tasks to be performed under the current plan
#         - task (:obj:`MeasurementTask`): task to be scheduled

#         ### Returns:
#         - winning_path (`list`): list indicating the best path if `task` was to be performed. 
#                             Is of type `NoneType` if no suitable path can be found for `task`.
#         - winning_bids (`dict`): dictionary mapping task IDs to their proposed bids if the winning 
#                             path is to be scheduled. Is of type `NoneType` if no suitable path can 
#                             be found.
#         - winning_path_utility (`float`): projected utility of executing the winning path
#         """
#         pass
    
#     def sum_path_utility(self, path : list, bids : dict) -> float:
#         """
#         Sums the utilities of a proposed path

#         ### Arguments:
#             - path (`list`): sequence of tasks dictionaries to be performed
#             - bids (`dict`): dictionary of task ids to the current task bid dictionaries 
#         """
#         utility = 0.0
#         for task in path:
#             task : MeasurementTask
#             bid : Bid = bids[task.id]
#             utility += bid.own_bid

#         return utility
    
#     @abstractmethod
#     def calc_utility(self, **kwargs) -> float:
#         """
#         Calculates the expected utility of performing a measurement task

#         ### Retrurns:
#             - utility (`float`): estimated normalized utility 
#         """
#         pass

#     def calc_imaging_time(self, state : SimulationAgentState, path : list, bids : dict, task : MeasurementTask) -> float:
#         """
#         Computes the earliest time when a task in the path would be performed

#         ### Arguments:
#             - state (obj:`SimulationAgentState`): state of the agent at the start of the path
#             - path (`list`): sequence of tasks dictionaries to be performed
#             - bids (`dict`): dictionary of task ids to the current task bid dictionaries 

#         ### Returns
#             - t_img (`float`): earliest available imaging time
#         """
#         # calculate the previous task's position and 
#         i = path.index(task)
#         if i == 0:
#             t_prev = state.t
#             pos_prev = state.pos
#         else:
#             task_prev : MeasurementTask = path[i-1]
#             bid_prev : Bid = bids[task_prev.id]
#             t_prev : float = bid_prev.t_img + task_prev.duration
#             pos_prev : list = task_prev.pos

#         # compute travel time to the task
#         t_img = state.calc_arrival_time(pos_prev, task.pos, t_prev)
#         return t_img if t_img >= task.t_start else task.t_start

#     def log_results(self, dsc : str, results : dict, level=logging.DEBUG) -> None:
#         """
#         Logs current results at a given time for debugging purposes

#         ### Argumnents:
#             - dsc (`str`): description of what is to be logged
#             - results (`dict`): results to be logged
#             - level (`int`): logging level to be used
#         """
#         out = f'\n{dsc}\ntask_id,  location,  bidder, bid, winner, winning_bid, t_img\n'
#         for task_id in results:
#             bid : Bid = results[task_id]
#             task = MeasurementTask(**bid.task)
#             split_id = task.id.split('-')
#             out += f'{split_id[0]}, {task.pos}, {bid.bidder}, {round(bid.own_bid, 3)}, {bid.winner}, {round(bid.winning_bid, 3)}, {round(bid.t_img, 3)}\n'

#         self.log(out, level)

#     def log_task_sequence(self, dsc : str, sequence : list, level=logging.DEBUG) -> None:
#         """
#         Logs a sequence of tasks at a given time for debugging purposes

#         ### Argumnents:
#             - dsc (`str`): description of what is to be logged
#             - sequence (`list`): list of tasks to be logged
#             - level (`int`): logging level to be used
#         """
#         out = f'\n{dsc} = ['
#         for task in sequence:
#             task : MeasurementTask
#             split_id = task.id.split('-')
            
#             if sequence.index(task) > 0:
#                 out += ', '
#             out += f'{split_id[0]}'
#         out += ']\n'

#         self.log(out,level)