import math
from messages import PlanMessage, AgentActionMessage, AgentStateMessage, SimulationMessageTypes
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

    async def listen(self) -> None:
        try:
            # listen for incoming broadcasts from other modules
            while True:
                await asyncio.sleep(1e6)

        except asyncio.CancelledError:
            return

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

    async def teardown(self) -> None:
        # nothing to tear-down
        return

class TaskBid(object):
    """
    ## Task Bid

    Describes a bid placed on a task by an agent

    ### Attributes:
        - task_id (`str`): id of the task being bid on
        - bidder (`bidder`): name of agent keeping track of this bid information
        - bid (`float` or `int`): current winning bid
        - winner (`str`): name of current the winning agent
        - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): lates time when this bid was updated
    """
    NONE = 'None'

    def __init__(self, 
                    task_id : str, 
                    bidder : str,
                    bid : Union[float, int] = 0, 
                    winner : str = NONE,
                    t_arrive : Union[float, int] = -1, 
                    t_update : Union[float, int] = -1
                    ) -> None:
        """
        Creates an instance of a task bid

        ### Arguments:
            - task_id (`str`): id of the task being bid on
            - bid (`float` or `int`): current winning bid
            - winner (`str`): name of current the winning agent
            - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): lates time when this bid was updated
        """
        self.task_id = task_id
        self.bidder = bidder
        self.bid = bid
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
        other : TaskBid = TaskBid(**other_dict)
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        
        if other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.bid > self.bid:
                    # update and rebroadcast
                    pass
                elif other.bid == self.bid:
                    # if there's a tie, bidder with the smallest id wins
                    _, their_id = other.bidder.split('_')
                    _, my_id = self.bidder.split('_')

                    their_id = int(their_id); my_id = int(my_id)

                    if their_id < my_id:
                        #update and rebroadcast
                        pass
                if other.bid < self.bid:
                    # update time and rebroadcast
                    pass

            elif self.winner == other.bidder:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    pass
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    pass
                elif other.t_update < self.t_update:
                    # leave and not reboradcast
                    pass

            elif self.winner not in [self.bidder, other.bidder]:
                if other.bid > self.bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    pass
                elif other.bid < self.bid and other.t_update <= self.t_update:
                    #leave and rebroadcast
                    pass
                elif other.bid == self.bid:
                    # leave and rebroadcast
                    pass
                elif other.bid < self.bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    pass
                elif other.bid > self.bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    pass

            elif self.winner == self.NONE:
                # update and rebroadcast
                pass

        elif other.winner == self.bidder:
            if self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    pass
                
            elif self.winner == other.bidder:
                # reset and rebroadcast with current update time
                pass

            elif self.winner not in [self.bidder, other.bidder]:
                # leave and rebroadcast
                pass

            elif self.winner == self.NONE:
                # leave and rebroadcast with current update time
                pass

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.bid > self.bid:
                    # update and rebroadcast
                    pass
                elif other.bid == self.bid:
                    # if there's a tie, bidder with the smallest id wins
                    _, their_id = other.bidder.split('_')
                    _, my_id = self.bidder.split('_')

                    their_id = int(their_id); my_id = int(my_id)

                    if their_id < my_id:
                        #update and rebroadcast
                        pass
                elif other.bid < self.bid:
                    # update time and rebroadcast
                    pass

            elif self.winner == other.bidder:
                # update and rebroadcast
                pass

            elif self.winner not in [self.bidder, other.bidder]:
                if other.t_update < self.t_update:
                    # update and rebroadcast
                    pass
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    pass
                elif other.t_update < self.t_update:
                    # leave and rebroadcast
                    pass

            elif self.winner not in [self.bidder, other.bidder, other.winner]:
                if other.bid > self.bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    pass
                elif other.bid < self.bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    pass
                elif other.bid < self.bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    pass
                elif other.bid > self.bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    pass

            elif self.winner == self.NONE:
                # update and rebroadcast
                pass

        elif other.winner is other.NONE:
            if self.winner == self.bidder:
                # leave and rebroadcast
                pass

            elif self.winner == other.bidder:
                # update and rebroadcast
                pass

            elif self.winner not in [self.bidder, other.bidder]:
                # update and rebroadcast
                pass

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                pass
        
        return None
    
    def __update_info(self,
                bid : Union[float, int], 
                winner : str,
                t_arrive : Union[float, int], 
                t_update : Union[float, int], 
                **_
                ) -> None:
        """
        Updates all of the variable bid information

        ### Arguments:
            - bid (`float` or `int`): current winning bid
            - winner (`str`): name of current the winning agent
            - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): lates time when this bid was updated
        """
        if t_update < self.t_update:
            # if update is from an older time than this bid, ignore update
            return

        self.bid = bid
        self.winner = winner
        self.t_arrive = t_arrive
        self.t_update = t_update

    def __update_time(self, t_update : Union[float, int]) -> None:
        """
        Only updates the time since this bid was last updated

        ### Arguments:
            - t_update (`float` or `int`): lates time when this bid was updated
        """
        self.t_update = t_update

    def __reset(self, t_update : Union[float, int]):
        """
        Resets the values of this bid while keeping track of lates update time

        ### Arguments:
            - t_update (`float` or `int`): lates time when this bid was updated
        """
        self.bid = 0
        self.winner = self.NONE
        self.t_arrive = -1
        self.t_update = t_update

    def __leave(self):
        """
        Leaves bid as is (used for algorithm readibility).
        """
        return

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

class ACCBBAPlannerModule(PlannerModule):
    def __init__(self,  
                results_path,
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
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
        self.results = {}
        self.active_tasks = []
    
    async def listen(self):
        # listen for any messages from the agent and adjust results ledger

        # if changes are made that affect the bundle, inform `routine()`
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
        
        except asyncio.CancelledError:
            return

    async def routine(self) -> None:
        # waits for changes in the ledger that may affect the current bundle
        pass