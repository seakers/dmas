from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Union
from applications.chess3d.messages import AgentActionMessage, AgentStateMessage, MeasurementRequestMessage, SensesMessage, SimulationMessageTypes
from applications.chess3d.nodes.orbitdata import OrbitData
from applications.chess3d.nodes.science.reqs import MeasurementRequest
from applications.chess3d.nodes.states import SatelliteAgentState, SimulationAgentState, SimulationAgentTypes, UAVAgentState
from dmas.messages import ManagerMessageTypes
from nodes.planning.planners import PlanningModule

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
            return False
            # raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.req_id}, given id: {other.task_id})')
        
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

class BidBuffer(object):
    """
    Asynchronous buffer that holds bid information for use by processes within the MACCBBA
    """
    
    def __init__(self) -> None:
        self.bid_access_lock = asyncio.Lock()
        self.bid_buffer = {}
        self.updated = asyncio.Event()             

    def __len__(self) -> int:
        l = 0
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : Bid
                l += 1 if bid is not None else 0
        return l

    async def pop_all(self) -> list:
        """
        Returns latest bids for all requests and empties buffer
        """
        await self.bid_access_lock.acquire()

        out = []
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : Bid
                if bid is not None:
                    # place bid in outgoing list
                    out.append(bid)

            # reset bids in buffer
            self.bid_buffer[req_id] = [None for _ in self.bid_buffer[req_id]]

        self.bid_access_lock.release()

        return out

    async def put_bid(self, new_bid : Bid) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        await self.bid_access_lock.acquire()

        if new_bid.req_id not in self.bid_buffer:
            req : MeasurementRequest = MeasurementRequest.from_dict(new_bid.req)
            self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

        current_bid : Bid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]
        
        if (    current_bid is None 
                or new_bid.bidder == current_bid.bidder
                or new_bid.t_update >= current_bid.t_update
            ):
            self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()

        self.bid_access_lock.release()

        self.updated.set()
        self.updated.clear()

    async def put_bids(self, new_bids : list) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        if len(new_bids) == 0:
            return

        await self.bid_access_lock.acquire()

        for new_bid in new_bids:
            new_bid : Bid

            if new_bid.req_id not in self.bid_buffer:
                req : MeasurementRequest = MeasurementRequest.from_dict(new_bid.req)
                self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

            current_bid : Bid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]

            if (    current_bid is None 
                 or (new_bid.bidder == current_bid.bidder and new_bid.t_update >= current_bid.t_update)
                 or (new_bid.bidder != new_bid.NONE and current_bid.winner == new_bid.NONE and new_bid.t_update >= current_bid.t_update)
                ):
                self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()

        self.bid_access_lock.release()

        self.updated.set()
        self.updated.clear()

    async def wait_for_updates(self, min_len : int = 1) -> list:
        """
        Waits for the contents of this buffer to be updated and to contain more updates than the given minimum
        """
        while True:
            await self.updated.wait()

            if len(self) >= min_len:
                break

        return await self.pop_all()

class ConsensusPlanner(PlannerModule):
    
    def __init__(   self, 
                    results_path: str, 
                    parent_name: str, 
                    parent_network_config: NetworkConfig, 
                    utility_func: Callable[[], Any], 
                    payload : list,
                    max_bundle_size = 4,
                    planning_horizon = 3600,
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:

        super().__init__(   results_path, 
                            parent_name, 
                            parent_network_config, 
                            utility_func, 
                            level, 
                            logger
                        )
        self.stats = {
                        "consensus" : [],
                        "planning" : [],
                        "doing" : [],
                        "c_comp_check" : [],
                        "c_t_end_check" : [],
                        "c_const_check" : []
                    }
        self.plan_history = []
        self.iter_counter = 0
        self.payload = payload
        self.max_bundle_size = max_bundle_size
        self.planning_horizon = planning_horizon
        self.parent_agent_type = None
    
    async def setup(self) -> None:
        await super().setup()

        self.listener_to_builder_buffer = BidBuffer()
        self.listener_to_broadcaster_buffer = BidBuffer()
        self.builder_to_broadcaster_buffer = BidBuffer()
        self.broadcasted_bids_buffer = BidBuffer()

        self.t_curr = 0
        self.agent_state : SimulationAgentState = None
        self.agent_state_lock = asyncio.Lock()
        self.agent_state_updated = asyncio.Event()
        self.parent_agent_type = None
        self.orbitdata = None
        self.plan_inbox = asyncio.Queue()

    async def live(self) -> None:
        """
        Performs three concurrent tasks:
        - Listener: receives messages from the parent agent and updates internal results
        - Bundle-builder: plans and bids according to local information
        - Planner: listens for requests from parent agent and returns latest plan to perform
        """
        try:
            listener_task = asyncio.create_task(self.listener(), name='listener()')
            bundle_builder_task = asyncio.create_task(self.bundle_builder(), name='bundle_builder()')
            planner_task = asyncio.create_task(self.planner(), name='planner()')
            
            tasks = [listener_task, bundle_builder_task, planner_task]

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
            # initiate results tracker
            results = {}
            level = logging.WARNING
            # level = logging.DEBUG

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

                    incoming_bids = []   
                    # if len(self.broadcasted_bids_buffer) > 0:
                    #     broadcasted_bids : list = await self.broadcasted_bids_buffer.pop_all()
                    #     incoming_bids.extend(broadcasted_bids)     

                    state : SimulationAgentState = None

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
                                                        
                            # update current state
                            await self.agent_state_lock.acquire()
                            state : SimulationAgentState = SimulationAgentState.from_dict(state_msg.state)

                            await self.update_current_time(state.t)
                            self.agent_state = state

                            if self.parent_agent_type is None:
                                if isinstance(state, SatelliteAgentState):
                                    # import orbit data
                                    self.orbitdata : OrbitData = self._load_orbit_data()
                                    self.parent_agent_type = SimulationAgentTypes.SATELLITE.value
                                elif isinstance(state, UAVAgentState):
                                    self.parent_agent_type = SimulationAgentTypes.UAV.value
                                else:
                                    raise NotImplementedError(f"states of type {state_msg.state['state_type']} not supported for greedy planners.")
                            
                            self.agent_state_lock.release()

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_REQ.value:
                            # unpack message 
                            req_msg = MeasurementRequestMessage(**sense)
                            req = MeasurementRequest.from_dict(req_msg.req)
                            self.log(f"received measurement request message!")
                            
                            # if not in send to planner
                            if req.id not in results:
                                # create task bid from measurement request and add to results
                                self.log(f"received new measurement request! Adding to results ledger...")

                                bids : list = SubtaskBid.subtask_bids_from_task(req, self.get_parent_name())
                                # results[req.id] = bids
                                incoming_bids.extend(bids)

                        elif sense['msg_type'] == SimulationMessageTypes.MEASUREMENT_BID.value:
                            # unpack message 
                            bid_msg = MeasurementBidMessage(**sense)
                            bid : SubtaskBid = SubtaskBid(**bid_msg.bid)
                            self.log(f"received measurement request message!")
                            
                            incoming_bids.append(bid)              
                    
                    # if len(self.broadcasted_bids_buffer) > 0:
                    #     broadcasted_bids : list = await self.broadcasted_bids_buffer.pop_all()
                    #     incoming_bids.extend(broadcasted_bids)   

                    if len(incoming_bids) > 0:
                        sorting_buffer = BidBuffer()
                        await sorting_buffer.put_bids(incoming_bids)
                        incoming_bids = await sorting_buffer.pop_all()

                        # results, bundle, path, \
                        # consensus_changes, rebroadcast_bids = self.consensus_phase( results, 
                        #                                                             [], 
                        #                                                             [], 
                        #                                                             self.get_current_time(),
                        #                                                             incoming_bids,
                        #                                                             'listener',
                        #                                                             level
                        #                                                         )
                        
                        # sorting_buffer = BidBuffer()
                        # await sorting_buffer.put_bids(rebroadcast_bids)
                        # rebroadcast_bids = await sorting_buffer.pop_all()

                        # self.log_changes("listener - CHANGES MADE FROM CONSENSUS", consensus_changes, level)
                        # self.log_changes("listener - REBROADCASTS TO BE DONE", rebroadcast_bids, level)

                        # send to bundle-builder and broadcaster
                        # await self.listener_to_builder_buffer.put_bids(rebroadcast_bids)
                        # await self.listener_to_broadcaster_buffer.put_bids(rebroadcast_bids)
                        await self.listener_to_builder_buffer.put_bids(incoming_bids)
                        await self.listener_to_broadcaster_buffer.put_bids(incoming_bids)

                    # inform planner of state update
                    self.agent_state_updated.set()
                    self.agent_state_updated.clear()
                    
                    await self.states_inbox.put(state) 

        except asyncio.CancelledError:
            return
        
        finally:
            self.listener_results = results
