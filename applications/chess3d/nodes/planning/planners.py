from dmas.modules import *
import numpy as np

class PlanningModule(InternalModule):
    def __init__(self, 
                results_path : str, 
                parent_name : str,
                module_network_config : NetworkConfig,
                parent_network_config: NetworkConfig, 
                utility_func : function,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
                       
        super().__init__(f'{parent_name}-PLANNING_MODULE', 
                        module_network_config, 
                        parent_network_config, 
                        level, 
                        logger)
        
        self.results_path = results_path
        self.parent_name = parent_name
        self.utility_func = utility_func

        self.stats = {}

    async def sim_wait(self, delay: float) -> None:
        return

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
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
    """
    NONE = 'None'
    
    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = NONE,
                    t_img : Union[float, int] = -1, 
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
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        """
        self.task = task
        self.task_id = task['id']
        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_img = t_img

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_img}'

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
        self.t_img = other.t_img

        if self.bidder == other.bidder:
            self.own_bid = other.own_bid

    @abstractmethod
    def reset(self, **kwargs) -> None:
        """
        Resets the values of this bid while keeping track of lates update time
        """
        self.winning_bid = 0
        self.winner = self.NONE
        self.t_img = -1

    def _leave(self, **kwargs) -> None:
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
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self != self._tie_breaker(self, other)

        return other.winning_bid > self.winning_bid

    def __gt__(self, other : object) -> bool:
        other : Bid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, use tie-breaker
            return self == self._tie_breaker(self, other)

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