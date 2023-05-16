from typing import Union
from planners.planners import *
import zmq 
from zmq import asyncio as azmq

"""
*********************************************************************************
   __________  ____  ___       ____  __                           
  / ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
 / /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
/ /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

class TaskBid(Bid):
    """
    ## Task Bid for CBBA 

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - task (`dict`): task being bid on
        - task_id (`str`): id of the task being bid on
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_arrive (`float` or `int`): time where the task is set to be performed by the winning agent
        - iterations (`dict`): list of latest iteration when this bid was updated
        - iter_converge (`float` or `int`): iterations interval after which global convergence is assumed to have been reached
    """

    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = Bid.NONE,
                    t_arrive : Union[float, int] = -1,
                    iter_converge : Union[float, int] = 0.0,
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
            - iter_converge (`float` or `int`): iterations interval after which global convergence is assumed to have been reached
        """
        super().__init__(task, bidder, winning_bid, own_bid, winner, t_arrive)
        self.iterations = {bidder : 0}
        self.iter_converge = iter_converge

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_arrive`, `t_update`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_arrive},{self.iter_update}'

    def get_update_iteration(self, target : str) -> Union[int, float]:
        """
        Returns the last known time of contact with the target agent.
        If no direct contact has been established, it returns the last time a contact was established with 
        another agent that was in contact with the target agent
        """
        if target not in self.iterations:
            iterations = [iteration for iteration in self.iterations]
            return max(iterations)
        else:
            return self.iterations[target]

    def update(self, other_dict : dict, iteration : Union[float, int]) -> object:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:
            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." 
            Proceedings of the 2011 American Control Conference. IEEE, 2011.

        ### Arguments:
            - other_dict (`dict`): dictionary representing the bid being compared to
            - iteration (`float` or `dict`): iteration in the cbba cycle when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): returns bid information to be rebroadcasted to other agents.
        """
        other : TaskBid = TaskBid(**other_dict)
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        # update iterations counter 
        self.iterations[other.bidder] = iteration

        if other.bidder == self.bidder:
            if other.iterations[other.bidder] > self.iterations[other.bidder]:
                self.__update_info(other)
                return self
        
        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    self.__update_info(other)
                    return self

            elif self.winner == other.bidder:
                self.__update_info(other)
                return self

            elif self.winner not in [self.bidder, other.bidder]:
                if (
                    other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner) 
                    or other.winning_bid > self.winning_bid
                    ):
                    self.__update_info(other)
                    return self

            elif self.winner == self.NONE:
                self.__update_info(other)
                return self

        elif other.winner == self.bidder:
            if self.winner == self.bidder:
                self.__leave()
                return None
                
            elif self.winner == other.bidder:
                self.reset()
                return self

            elif self.winner not in [self.bidder, other.bidder]:
                if other.get_update_iteration(self.winner) > self.get_update_iteration(self.winner):
                    self.reset()
                    return self

            elif self.winner == self.NONE:
                self.__leave()
                return None

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if (
                    other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner) 
                    and other.winning_bid > self.winning_bid
                    ):
                    self.__update_info(other)
                    return self

            elif self.winner == other.bidder:
                if other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner):
                    self.__update_info(other)
                else:
                    self.reset()
                return self

            elif self.winner == other.winner:
                if other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner):
                    self.__update_info(other)
                    return self

            elif self.winner not in [self.bidder, other.bidder, other.winner]:
                if other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner):
                    if (
                        other.get_update_iteration(self.winner) > self.get_update_iteration(self.winner)
                        or other.winning_bid > self.winning_bid
                        ):
                        self.__update_info(other)
                        return self
                elif other.get_update_iteration(self.winner) > self.get_update_iteration(self.winner):
                    self.reset()
                    return self

            elif self.winner == self.NONE:
                if other.get_update_iteration(other.winner) > self.get_update_iteration(other.winner):
                    self.__update_info(other)
                    return self

        elif other.winner is other.NONE:
            if self.winner == self.bidder:
                self.__leave()
                return None

            elif self.winner == other.bidder:
                self.__update_info(other)

            elif self.winner not in [self.bidder, other.bidder]:
                if other.get_update_iteration(self.winner) > self.get_update_iteration(self.winner):
                    self.__update_info(other)
                    return self

            elif self.winner == self.NONE:
                self.__leave()
                return None
        
        return None
    
    def __update_info(self, other) -> None:
        """
        Updates all of the variable bid information

        ### Arguments:
            - other (`TaskBid`): equivalent bid being used to update information
        """

        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id}).')

        other : TaskBid
        self.winning_bid = other.winning_bid
        self.winner = other.winner
        self.t_arrive = other.t_arrive

        if other.winner not in self.iterations:
            self.iterations[other.winner] = other.iterations[other.winner]
        if self.iterations[other.winner] > self.iterations[other.winner]:
            self.iterations[other.winner] = other.iterations[other.winner]

        if self.bidder == other.bidder:
            self.own_bid = other.own_bid

    def reset(self) -> None:
        """
        Resets the values of this bid while keeping track of lates update time
        """
        self.winning_bid = 0
        self.winner = self.NONE
        self.t_arrive = -1

    def __leave(self):
        """
        Leaves bid as is (used for algorithm readibility).

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        return
    
    def __lt__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, bidder with the smallest id wins
            _, their_id = other.winner.split('_')
            _, my_id = self.winner.split('_')
            their_id = int(their_id); my_id = int(my_id)

            return their_id < my_id

        return other.winning_bid > self.winning_bid

    def __le__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid >= self.winning_bid

    def __gt__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if other.winning_bid == self.winning_bid:
            # if there's a tie, bidder with the smallest id wins

            if other.winner == self.NONE and self.winner != self.NONE:
                return True
            elif other.winner != self.NONE and self.winner == self.NONE:
                return False
            elif other.winner == self.NONE and self.winner == self.NONE:
                return True

            _, their_id = other.winner.split('_')
            _, my_id = self.winner.split('_')
            their_id = int(their_id); my_id = int(my_id)

            return their_id > my_id

        return other.winning_bid < self.winning_bid

    def __ge__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        if abs(other.winning_bid - self.winning_bid) < 1e-3:
            return True

        return other.winning_bid <= self.winning_bid

    def __eq__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        return abs(other.winning_bid - self.winning_bid) < 1e-3 and other.winning_bid == self.winning_bid

    def __ne__(self, other : object) -> bool:
        other : TaskBid
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot compare bids intended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
        return abs(other.winning_bid - self.winning_bid) > 1e-3 or other.winning_bid != self.winning_bid

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        return TaskBid(self.task, self.bidder, self.winning_bid, self.winner, self.t_arrive, self.iter_update)

class CBBAPlannerModule(ConsensusPlanner):
    """
    # Synchronous Consensus-Based Bundle Algorithm Planner
    """
    def __init__(   
                self, 
                results_path: str, 
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                l_bundle: int, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        """
        Creates an intance of a CBBA Planner Module
        
        ### Arguments:
            - results_path (`str`): path for printing this planner's results
            - manager_port (`int`): localhost port used by the parent agent
            - agent_id (`int`): iddentification number for the parent agent
            - parent_network_config (:obj:`NetworkConfig`): network config of the parent agent
            - l_bundle (`int`): maximum bundle size
            - level (`int`): logging level
            - logger (`logging.Logger`): logger being used 
        """
        super().__init__(results_path, manager_port, agent_id, parent_network_config, PlannerTypes.CBBA, l_bundle, level, logger)

    async def live(self) -> None:
        try:
            results = {}
            while True:
                bundle, path, results =await self.planning(results)

                incoming_bids = await self.execute_plan(bundle, path)
        finally:
            pass

    async def listen_to_parent(self) -> list:
        """
        Listens for any incoming transmissions from the parent agent and transforms them into a list of SimulationMessage objects
        """
        poller = azmq.Poller()
        

    async def planning(self, results : dict) -> tuple:
        """
        Iterates between bundle-building phase and consensus phase to create a sequence of tasks to perform by the agent
        """
        while True:
            pass


    async def execute_plan(self, bundle : list, path : list) -> tuple:
        """
        Listens to agent's senses and informs it of what next action to take based on consensus-built plan
        """
        pass