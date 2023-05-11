from typing import Union
"""
*********************************************************************************
   __________  ____  ___       ____  __                           
  / ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
 / /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
/ /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

class TaskBid(object):
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
    NONE = 'None'

    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = NONE,
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
        self.task = task
        self.task_id = task['id']
        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_arrive = t_arrive
        self.iterations = {bidder : 0}
        self.iter_converge = iter_converge

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_arrive`, `t_update`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_arrive},{self.iter_update}'

    def update(self, other_dict : dict, iteration : Union[float, int]) -> None:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:
            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." Proceedings of the 2011 American Control Conference. IEEE, 2011.

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
        
        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    self.__update_info(other)

            elif self.winner == other.bidder:
                self.__update_info(other)

            elif self.winner not in [self.bidder, other.bidder]:
                if self.winner not in other.iterations:
                    if other.winning_bid > self.winning_bid:
                        self.__update_info(other)
                else:
                    if other.iterations[self.winner] > self.iterations[self.winner] or other.winning_bid > self.winning_bid:
                        self.__update_info(other)

            elif self.winner == self.NONE:
                self.__update_info(other)

        elif other.winner == self.bidder:
            if self.winner == self.bidder:
                self.__leave()
                
            elif self.winner == other.bidder:
                self.reset()

            elif self.winner not in [self.bidder, other.bidder]:
                if self.winner not in other.iterations:
                    self.__leave()
                elif other.iterations[self.winner] > self.iterations[self.winner]:
                    self.reset()

            elif self.winner == self.NONE:
                self.__leave()

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winner not in self.iterations:
                    if other.winning_bid > self.winning_bid:
                        self.__update_info(other)
                else:
                    if other.iterations[other.winner] >  self.iterations[other.winner] and other.winning_bid > self.winning_bid:
                        self.__update_info(other)

            elif self.winner == other.bidder:
                if other.winner not in self.iterations:
                    self.__update_info(other)
                elif other.iterations[other.winner] >  self.iterations[other.winner]:
                    self.__update_info(other)
                else:
                    self.reset(iteration)

            elif self.winner == other.winner:
                if other.winner not in self.iterations:
                    self.__update_info(other)
                elif other.iterations[other.winner] >  self.iterations[other.winner]:
                    self.__update_info(other)

            elif self.winner not in [self.bidder, other.bidder, other.winner]:
                pass

            elif self.winner == self.NONE:
                if other.winner not in self.iterations:
                    if self.winner not in other.iterations:
                        self.__leave()
                    elif other.iterations[self.winner] > self.iterations[self.winner]:
                        self.__update_info(other)
                    elif other.winning_bid > self.winning_bid:
                        self.__update_info(other)

                elif other.iterations[other.winner] > self.iterations[other.winner]:
                    if self.winner not in other.iterations:
                        self.__leave()
                    elif other.iterations[self.winner] > self.iterations[self.winner]:
                        self.__update_info(other)
                    elif other.winning_bid > self.winning_bid:
                        self.__update_info(other)

                elif self.winner not in other.iterations:
                    self.__leave()

                elif other.iterations[self.winner] > self.iterations[self.winner]:
                    if other.winner not in self.iterations:
                        self.__leave()

                    elif self.iterations[other.winner] > other.iterations[other.winner]:
                        self.reset()

        elif other.winner is other.NONE:
            if self.winner == self.bidder:
                self.__leave()

            elif self.winner == other.bidder:
                self.__update_info(other)

            elif self.winner not in [self.bidder, other.bidder]:
                if other.winner not in other.iterations:
                    self.__leave()
                elif other.iterations[self.winner] > self.iterations[self.winner]:
                    self.__update_info(other)

            elif self.winner == self.NONE:
                self.__leave()
        
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