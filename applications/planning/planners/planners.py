from dmas.modules import *

class PlannerTypes(Enum):
    FIXED = 'FIXED'     # Fixed pre-determined plan
    CBBA = 'CCBBA'      # Synchronous Consensus-Based Bundle Algorithm
    ACBBA = 'ACBBA'     # Asynchronous Consensus-Based Bundle Algorithm
    CCBBA = 'CCBBA'     # Synchronous Consensus Constraint-Based Bundle Algorithm
    ACCBBA = 'ACCBBA'   # Asynchronous Consensus Constraint-Based Bundle Algorithm

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
                                                zmq.PUB: [f'tcp://*:{manager_port+6 + 4*agent_id + 3}'],
                                                zmq.SUB: [f'tcp://localhost:{manager_port+6 + 4*agent_id + 2}'],
                                                zmq.PUSH: [f'tcp://localhost:{manager_port+3}']})
                
        super().__init__(f'PLANNING_MODULE_{agent_id}', 
                        module_network_config, 
                        parent_network_config, 
                        level, 
                        logger)
        
        if planner_type not in PlannerTypes:
            raise NotImplementedError(f'planner of type {planner_type} not yet supported.')
        self.planner_type = planner_type
        self.results_path = results_path
        self.parent_id = agent_id

    async def sim_wait(self, delay: float) -> None:
        return

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

class Bid(ABC):
    """
    ## Task Bid for Consensus Algorithm Planners

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - task (`dict`): task being bid on
        - task_id (`str`): id of the task being bid on
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
    """
    NONE = 'None'
    
    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = NONE,
                    t_arrive : Union[float, int] = -1, 
                    **_
                    ) -> object:
        """
        Creates an instance of a task bid

        ### Arguments:
            - task (`dict`): task being bid on
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
        """
        self.task = task
        self.task_id = task['id']
        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_arrive = t_arrive

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_arrive`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_arrive}'

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
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id}).')

        other : Bid
        self.winning_bid = other.winning_bid
        self.winner = other.winner
        self.t_arrive = other.t_arrive

        if self.bidder == other.bidder:
            self.own_bid = other.own_bid

    @abstractmethod
    def reset(self, **kwargs) -> None:
        """
        Resets the values of this bid while keeping track of lates update time
        """
        self.winning_bid = 0
        self.winner = self.NONE
        self.t_arrive = -1

    def _leave(self, **kwargs) -> None:
        """
        Leaves bid as is (used for algorithm readibility).

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        return

    def __tie_breaker(self, bid1 : object, bid2 : object) -> object:
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
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self != self.__tie_breaker(self, other)

        return other.winning_bid > self.winning_bid

    def __gt__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self == self.__tie_breaker(self, other)

        return other.winning_bid < self.winning_bid

    def __le__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid >= self.winning_bid

    def __ge__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid <= self.winning_bid

    def __eq__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        return abs(other.winning_bid - self.winning_bid) < 1e-3 and other.winner == self.winner

    def __ne__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
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

class ConsensusPlanner(PlannerModule):
    pass