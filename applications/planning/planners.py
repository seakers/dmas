import math
from messages import *
from states import SimulationAgentState
from tasks import IdleAction, MoveAction, MeasurementTask
from dmas.agents import AgentAction
from dmas.modules import *

class PlannerTypes(Enum):
    ACCBBA = 'ACCBBA'   # Asynchronous Consensus Constraint-Based Bundle Algorithm
    FIXED = 'FIXED'     # Fixed pre-determined plan

class PlannerResults(ABC):
    @abstractmethod
    def __eq__(self, __o: object) -> bool:
        """
        Compares two results 
        """
        return super().__eq__(__o)

class PlannerModule(InternalModule):
    def __init__(self, 
                results_path : str, 
                manager_port : int,
                agent_id : int,
                parent_network_config: NetworkConfig, 
                planner_type : PlannerTypes,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        module_network_config =  NetworkConfig(f'AGENT_{agent_id}',
                                                manager_address_map = {
                                                zmq.REQ: [],
                                                zmq.PUB: [f'tcp://*:{manager_port+5 + 4*agent_id + 3}'],
                                                zmq.SUB: [f'tcp://localhost:{manager_port+5 + 4*agent_id + 2}']})
                
        super().__init__(f'PLANNING_MODULE_{agent_id}', 
                        module_network_config, 
                        parent_network_config, 
                        [], 
                        level, 
                        logger)
        
        if planner_type not in PlannerTypes:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')
        self.planner_type = planner_type
        self.results_path = results_path
        self.parent_id = agent_id

    async def empty_manager_inbox(self) -> list:
        msgs = []
        while True:
            # wait for manager messages
            self.log('waiting for parent agent message...')
            _, _, content = await self.manager_inbox.get()
            msgs.append(content)

            # wait for any current transmissions to finish being received
            self.log('waiting for any possible transmissions to finish...')
            await asyncio.sleep(0.01)

            if self.manager_inbox.empty():
                self.log('manager queue empty.')
                break
            self.log('manager queue still contains elements.')
        
        return msgs
class FixedPlannerModule(PlannerModule):
    def __init__(self, 
                results_path : str, 
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(results_path,
                         manager_port, 
                         agent_id, 
                         parent_network_config, 
                         PlannerTypes.FIXED, 
                         level, 
                         logger)
        
    async def setup(self) -> None:
        # create an initial plan
        dt = 1
        steps = 1 * (self.parent_id + 1)
        pos = [steps, steps]
        t_start = math.sqrt( pos[0]**2 + pos[1]**2 ) + dt
        
        travel_to_target = MoveAction(pos, dt)
        measure = MeasurementTask(pos, 1, ['VNIR'], t_start, t_end=1e6)
        return_to_origin = MoveAction([0,0], t_start)

        self.plan = [
                    travel_to_target,
                    measure,
                    return_to_origin
                    ]
        
    async def listen(self) -> None:
        try:
            # does nothing
            while True:
                await asyncio.sleep(1e6)

        except asyncio.CancelledError:
            return
    
    async def routine(self) -> None:
        try:
            self.log('initial plan sent!')
            t_curr = 0
            while True:
                # listen for agent to send new senses
                self.log('waiting for incoming senses from parent agent...')
                senses = await self.empty_manager_inbox()

                self.log(f'received {len(senses)} senses from agent! processing senses...')
                new_plan = []
                for sense in senses:
                    sense : dict
                    if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                        # unpack message 
                        msg : AgentActionMessage = AgentActionMessage(**sense)
                        
                        if msg.status != AgentAction.COMPLETED and msg.status != AgentAction.ABORTED:
                            # if action wasn't completed, re-try
                            action_dict : dict = msg.action
                            self.log(f'action {action_dict} not completed yet! trying again...')
                            msg.dst = self.get_parent_name()
                            new_plan.append(action_dict)

                        elif msg.status == AgentAction.COMPLETED:
                            # if action was completed, remove from plan
                            action_dict : dict = msg.action
                            completed_action = AgentAction(**action_dict)
                            removed = None
                            for action in self.plan:
                                action : AgentAction
                                if action.id == completed_action.id:
                                    removed = action
                                    break

                            if removed is not None:
                                self.plan.remove(removed)

                    elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # unpack message 
                        msg : AgentStateMessage = AgentStateMessage(**sense)
                        state = SimulationAgentState(**msg.state)

                        # update current simulation time
                        if t_curr < state.t:
                            t_curr = state.t               

                if len(new_plan) == 0:
                    # no previously submitted actions will be re-attempted
                    for action in self.plan:
                        action : AgentAction
                        if action.t_start <= t_curr <= action.t_end:
                            new_plan.append(action.to_dict())
                            break

                    if len(new_plan) == 0:
                        # if no plan left, just idle for a time-step
                        self.log('no more actions to perform. instruct agent to idle for one time-step.')
                        t_idle = 1e6
                        for action in self.plan:
                            action : AgentAction
                            t_idle = action.t_start if action.t_start < t_idle else t_idle
                        
                        action = IdleAction(t_curr, t_idle)
                        new_plan.append(action.to_dict())

                self.log(f'sending {len(new_plan)} actions to agent...')
                plan_msg = PlanMessage(self.get_element_name(), self.get_network_name(), new_plan)
                await self._send_manager_msg(plan_msg, zmq.PUB)

                self.log(f'actions sent!')

        except asyncio.CancelledError:
            return
        
        except Exception as e:
            self.log(f'routine failed. {e}')
            raise e

    async def teardown(self) -> None:
        # nothing to tear-down
        return

"""
*********************************************************************************
    ___   ________________  ____  ___       ____  __                           
   /   | / ____/ ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
  / /| |/ /   / /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
 / ___ / /___/ /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
/_/  |_\____/\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

class ACCBBATaskBid(object):
    """
    ## ACCBBA Task Bid

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - task (`dict`): task being bid on
        - task_id (`str`): id of the task being bid on
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - bid (`float` or `int`): current winning bid
        - winner (`str`): name of current the winning agent
        - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): lates time when this bid was updated
    """
    NONE = 'None'

    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = NONE,
                    t_arrive : Union[float, int] = -1, 
                    t_update : Union[float, int] = -1,
                    **_
                    ) -> object:
        """
        Creates an instance of a task bid

        ### Arguments:
            - task_id (`str`): id of the task being bid on
            - bid (`float` or `int`): current winning bid
            - winner (`str`): name of current the winning agent
            - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        self.task = task
        self.task_id = task['id']
        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_arrive = t_arrive
        self.t_update = t_update

    def update(self, other_dict : dict, t : Union[float, int]) -> object:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:

            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." Proceedings of the 2011 American Control Conference. IEEE, 2011.
        ### Arguments
            - other_dict (`dict`): dictionary representing the bid being compared to
            - t (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): returns information to be rebroadcasted to agents.
        """
        other : ACCBBATaskBid = ACCBBATaskBid(**other_dict)
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        
        if other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other
                    
                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    _, their_id = other.bidder.split('_')
                    _, my_id = self.bidder.split('_')
                    their_id = int(their_id); my_id = int(my_id)

                    if their_id < my_id:
                        # update and rebroadcast
                        self.__update_info(other, t)
                        return other

                if other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return self

            elif self.winner == other.bidder:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self.__leave(t)
                    return None

                elif other.t_update < self.t_update:
                    # leave and not rebroadcast
                    self.__leave(t)
                    return None

            elif self.winner not in [self.bidder, other.bidder]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    #leave and rebroadcast
                    self.__leave(t)
                    return self

                elif other.winning_bid == self.winning_bid:
                    # leave and rebroadcast
                    self.__leave(t)
                    return self

                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

            elif self.winner == self.NONE:
                # update and rebroadcast
                self.__update_info(other, t)
                return other

        elif other.winner == self.bidder:
            if self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self.__leave()
                    return None
                
            elif self.winner == other.bidder:
                # reset and rebroadcast with current update time
                self.__reset(t)
                return self

            elif self.winner not in [self.bidder, other.bidder]:
                # leave and rebroadcast
                self.__leave(t)
                return self

            elif self.winner == self.NONE:
                # leave and rebroadcast with current update time
                self.__update_time(t)
                return self

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    _, their_id = other.bidder.split('_')
                    _, my_id = self.bidder.split('_')

                    their_id = int(their_id); my_id = int(my_id)

                    if their_id < my_id:
                        #update and rebroadcast
                        self.__update_info(other, t)
                        return other

                elif other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time
                    return other

            elif self.winner == other.bidder:
                # update and rebroadcast
                self.__update_info(other, t)
                return other

            elif self.winner not in [self.bidder, other.bidder]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other
                    
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self.__leave(t)
                    return None

                elif other.t_update < self.t_update:
                    # leave and rebroadcast
                    self.__leave(t)
                    return self

            elif self.winner not in [self.bidder, other.bidder, other.winner]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    self.__leave(t)
                    return self
                    
                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    self.__leave(t)
                    return self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self.__update_info(other, t)
                return other

        elif other.winner is other.NONE:
            if self.winner == self.bidder:
                # leave and rebroadcast
                self.__leave(t)
                return self

            elif self.winner == other.bidder:
                # update and rebroadcast
                self.__update_info(other, t)
                return other

            elif self.winner not in [self.bidder, other.bidder]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self.__update_info(other, t)
                    return other

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                self.__leave(t)
                return self
        
        return None
    
    def __update_info(self,
                other, 
                t : Union[float, int]
                ) -> None:
        """
        Updates all of the variable bid information

        ### Arguments:
            - other (`TaskBid`): equivalent bid being used to update information
            - t (`float` or `dict`): time when this information is being updated
        """
        if t < self.t_update:
            # if update is from an older time than this bid, ignore update
            raise ValueError(f'attempting to update bid with outdated information.')

        elif self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id}).')

        other : ACCBBATaskBid
        self.winning_bid = other.bid
        self.winner = other.winner
        self.t_arrive = other.t_arrive
        self.t_update = t

    def __update_time(self, t_update : Union[float, int]) -> None:
        """
        Only updates the time since this bid was last updated

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        self.t_update = t_update

    def __reset(self, t_update : Union[float, int]):
        """
        Resets the values of this bid while keeping track of lates update time

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        self.winning_bid = 0
        self.winner = self.NONE
        self.t_arrive = -1
        self.t_update = t_update

    def __leave(self, t : Union[float, int]):
        """
        Leaves bid as is (used for algorithm readibility).

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        return

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        return ACCBBATaskBid(self.task, self.bidder, self.winning_bid, self.winner, self.t_arrive, self.t_update)

class ACCBBAPlannerModule(PlannerModule):
    def __init__(self,  
                results_path,
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                l_bundle: int,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(   results_path,
                            manager_port, 
                            agent_id, 
                            parent_network_config,
                            PlannerTypes.ACCBBA, 
                            level, 
                            logger)

        if not isinstance(l_bundle, int) and not isinstance(l_bundle, float):
            raise AttributeError(f'`l_bundle` must be of type `int` or `float`; is of type `{type(l_bundle)}`')
        
        self.parent_name = f'AGENT_{agent_id}'
        self.l_bundle = l_bundle

        self.t_curr = 0.0
        self.state_curr = None
        self.results = {}
    
    async def setup(self) -> None:
        # initialize internal messaging queues
        self.bundle_builder_inbox = asyncio.Queue()

        self.alternate_outgoing = True
        self.outgoing_listen_inbox = asyncio.Queue()
        self.outgoing_bundle_builder_inbox = asyncio.Queue()

        # initialize results lock
        self.results_lock = asyncio.Lock()

    async def listen(self):
        # listen for any messages from the agent and adjust results ledger

        # if changes are made that affect the bundle, inform `routine()`
        try:
            while True:
                # listen for agent to send new senses
                self.log('waiting for incoming senses from parent agent...')
                senses = await self.empty_manager_inbox()

                self.log(f'received {len(senses)} senses from agent! processing senses...')
                for sense in senses:
                    sense : dict
                    if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                        # unpack message 
                        msg : AgentActionMessage = AgentActionMessage(**sense)
                        
                        # send to bundle builder 
                        await self.bundle_builder_inbox.put(msg)

                    elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # unpack message 
                        msg : AgentStateMessage = AgentStateMessage(**sense)
                        
                        # send to bundle builder 
                        await self.bundle_builder_inbox.put(msg) 

                    elif sense['msg_type'] == SimulationMessageTypes.TASK_BID.value:
                        # unpack message 
                        bid_msg : TaskBidMessage = TaskBidMessage(**sense)
                        their_bid = ACCBBATaskBid(**bid_msg.bid)

                        # acquire results lock
                        await self.results_lock.acquire()

                        if their_bid.task_id not in self.results:
                            # bid is for a task that I was not aware of; create new empty bid for it and compare
                            my_bid = ACCBBATaskBid(their_bid.task, self.get_parent_name())
                            self.results[their_bid.task_id] = my_bid
                        
                        # compare bid 
                        my_bid : ACCBBATaskBid = self.results[their_bid.task_id]
                        broadcast_bid : ACCBBATaskBid = my_bid.update(their_bid.to_dict())
                        
                        # release results lock
                        self.results_lock.release()

                        if broadcast_bid is not None:
                            # if relevant changes were made, send to bundle builder and to out-going inbox 
                            out_msg = TaskBidMessage(   
                                                    self.get_element_name(), 
                                                    self.get_parent_name(), 
                                                    broadcast_bid.to_dict()
                                                )
                            await self.bundle_builder_inbox.put(out_msg)
                            await self.outgoing_listen_inbox.put(out_msg) 

                    elif sense['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                        # unpack message
                        task_req = TaskRequest(**sense)

                        # acquire results lock
                        await self.results_lock.acquire()

                        # create task bid from task request and add to results
                        task_dict : dict = task_req.task
                        task = TaskRequest(**task_dict)
                        bid = ACCBBATaskBid(task, self.get_parent_name())
                        self.results[task.id] = bid

                        # send to bundle-builder
                        out_msg = TaskBidMessage(   
                                                    self.get_element_name(), 
                                                    self.get_parent_name(), 
                                                    bid.to_dict()
                                                )
                        await self.bundle_builder_inbox.put(out_msg)

                        # release results lock
                        self.results_lock.release()

        except asyncio.CancelledError:
            return

    async def bundle_builder(self) -> None:
        """
        Bundle-builder

        Performs periodic checks on the received messages from the listener and
        creates a plan based.
        """
        bundle = []
        try:
            while True:
                # wait for periodic message check

                # if no messages received, wait again

                # if messages exist, process all messages from listener 
                pass

        except asyncio.CancelledError:
            pass

    async def rebroadcaster(self) -> None:
        try:
            while True:
                # wait for both outgoing inboxes to not be empty

                # discard all repeating bids from both inboxes, only keep the most updated one from each

                # compare bundle results from the builder and changes from the listener

                # if 
                
                pass

        except asyncio.CancelledError:
            pass

    async def routine(self) -> None:
        
        
        # if msg.status != AgentAction.COMPLETED and msg.status != AgentAction.ABORTED:
        #     # if action wasn't completed, re-try
        #     action_dict : dict = msg.action
        #     self.log(f'action {action_dict} not completed yet! trying again...')
        #     msg.dst = self.get_parent_name()
        #     new_plan.append(action_dict)

        # elif msg.status == AgentAction.COMPLETED:
        #     # if action was completed, remove from plan
        #     action_dict : dict = msg.action
        #     completed_action = AgentAction(**action_dict)
        #     removed = None
        #     for action in self.plan:
        #         action : AgentAction
        #         if action.id == completed_action.id:
        #             removed = action
        #             break

        #     if removed is not None:
        #         self.plan.remove(removed)

        pass

    async def teardown(self) -> None:
        return