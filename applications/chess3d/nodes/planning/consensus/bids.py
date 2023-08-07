from abc import ABC, abstractmethod
import asyncio
from enum import Enum
from typing import Union
import numpy as np

from applications.chess3d.nodes.science.reqs import MeasurementRequest

class BidTypes(Enum):
    UNCONSTRAINED_BID = 'UNCONSTRAINED_BID'
    CONSTRAINED_BID = 'CONSTRAINED_BID'
    GREEDY = 'GREEDY'

class Bid(ABC):
    """
    ## Measurement Request Bid for Consensus Planners

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - bid_type (`str`): type of bid being placed
        - req (`dict`): measurement request being bid on
        - subtask_index (`int`) : index of the subtask to be bid on
        - main_measurement (`str`): name of the main measurement assigned by this subtask bid
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
        - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
        - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
    """

    NONE = 'None'
    
    def __init__(   self, 
                    bid_type : str,
                    req: dict, 
                    subtask_index : int,
                    main_measurement : str,
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    dt_converge: Union[float, int] = 0.0,
                    performed : bool = False,
                    ) -> object:
        """
        Creates an instance of a task bid

        ### Arguments:
            - bid_type (`str`): type of bid being placed
            - req (`dict`): measurement request being bid on
            - subtask_index (`int`) : index of the subtask to be bid on
            - main_measurement (`str`): name of the main measurement assigned by this subtask bid
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
            - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
            - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
        """
        self.bid_type = bid_type
        self.req = req
        self.req_id = req['id']
        
        self.subtask_index = subtask_index
        self.main_measurement = main_measurement

        self.bidder = bidder
        self.winning_bid = winning_bid
        self.own_bid = own_bid
        self.winner = winner
        self.t_img = t_img
        self.t_update = t_update

        self.N_req = 0
        self.dt_converge = dt_converge
        self.performed = performed

    """
    ------------------
    COMPARISON METHODS
    ------------------
    """

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
        
        return abs(other.winning_bid - self.winning_bid) < 1e-3 and other.winner == self.winner

    def __ne__(self, other : object) -> bool:
        other : Bid
        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            return True
        
        return abs(other.winning_bid - self.winning_bid) > 1e-3 or other.winner != self.winner

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
        broadcast_out, changed = self._update_rules(other_dict, t)
        broadcast_out : Bid; changed : bool

        if broadcast_out is not None:
            other = ConstrainedBid(**other_dict)
            if other.bidder == broadcast_out.bidder:
                return other, changed
            else:
                return self, changed
        return None, changed

    def _update_rules(self, other_dict : dict, t : Union[float, int]) -> tuple:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:
            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." Proceedings of the 2011 American Control Conference. IEEE, 2011.

        ### Arguments:
            - other_dict (`dict`): dictionary representing the bid being compared to
            - t (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): bid information to be rebroadcasted to other agents.
            - changed (`bool`): boolean value indicating if a change was made to this bid
        """
        other : ConstrainedBid = ConstrainedBid(**other_dict)
        prev : ConstrainedBid = self.copy() 

        if self.req_id != other.req_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        if other.bidder == self.bidder:
            if other.t_update > self.t_update:
                self._update_info(other,t)
                return self, prev!=self
            else:
                self._leave(t)
                return None, False
        
        elif other.winner == other.NONE:
            if self.winner == self.bidder:
                # leave and rebroadcast
                self._leave(t)
                return self, False

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                self._leave(t)
                return None, False

        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev!=self

                if other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return self, prev!=self

            elif self.winner == other.bidder:
                # if abs(other.t_update - self.t_update) < 1e-6:
                #     # leave and no rebroadcast
                #     self._leave(t)
                #     return None, False

                if other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.t_update < self.t_update:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    #leave and rebroadcast
                    self._leave(t)
                    return self, False

                elif other.winning_bid == self.winning_bid:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False

                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self

        elif other.winner == self.bidder:
            if self.winner == self.NONE:
                # leave and rebroadcast with current update time
                self.__update_time(t)
                return self, prev!=self

            elif self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False
                
            elif self.winner == other.bidder and other.bidder != self.bidder:
                # reset and rebroadcast with current update time
                self.reset(t)
                return self, prev!=self

            elif self.winner not in [self.bidder, other.bidder, self.NONE]:
                # leave and rebroadcast
                self._leave(t)
                return self, False

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other, prev!=self

                elif other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return other, prev!=self

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self

            elif self.winner == other.winner:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None, False

                elif other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False

            elif self.winner not in [self.bidder, other.bidder, other.winner, self.NONE]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, False
                    
                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other, prev!=self
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self, prev!=self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other, prev!=self
        
        return None, prev!=self

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

    def set_bid(self, new_bid : Union[int, float], t_img : Union[int, float], t_update : Union[int, float]) -> None:
        """
        Sets new values for this bid

        ### Arguments: 
            - new_bid (`int` or `float`): new bid value
            - t_img (`int` or `float`): new imaging time
            - t_update (`int` or `float`): update time
        """
        self.own_bid = new_bid
        self.winning_bid = new_bid
        self.winner = self.bidder
        self.t_img = t_img
        self.t_update = t_update

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `subtask_index`, `main_measurement`, `dependencies`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`, `t_update`
        """
        req : MeasurementRequest = MeasurementRequest.from_dict(self.req)
        split_id = req.id.split('-')
        line_data = [   split_id[0], 
                        self.subtask_index, 
                        self.main_measurement, 
                        req.lat_lon_pos, 
                        self.bidder, 
                        round(self.own_bid, 3), 
                        self.winner, 
                        round(self.winning_bid, 3), 
                        round(self.t_img, 3)
                    ]
        out = ""
        for i in range(len(line_data)):
            line_datum = line_data[i]
            out += str(line_datum)
            if i < len(line_data) - 1:
                out += ','

        return out

    @abstractmethod
    def new_bids_from_request(req : MeasurementRequest, bidder : str) -> list:
        pass

    def has_winner(self) -> bool:
        """
        Checks if this bid has a winner
        """
        return self.winner != Bid.NONE
    
    """
    ---------------------------
    COPY AND OTHER CONSTRUCTORS
    ---------------------------
    """
    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        return self.from_dict(self.to_dict())

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

    def from_dict(d : dict) -> object:
        """
        Creates a bid class object from a dictionary
        """
        if d['bid_type'] == BidTypes.UNCONSTRAINED_BID.value:
            return UnconstrainedBid(**d)
        elif d['bid_type'] == BidTypes.CONSTRAINED_BID.value:
            return ConstrainedBid(**d)
        elif d['bid_type'] == BidTypes.GREEDY.value:
            return GreedyBid(**d)
        else:
            raise AttributeError(f"bids of type `{d['bid_type']}` not yet supported.")
        

class UnconstrainedBid(Bid):
    """
    ## Unconstrained Bid

    Describes a bid placed on a measurement request that has no constraints

    ### Attributes:
        - bid_type (`str`): type of bid being placed
        - req (`dict`): measurement request being bid on
        - subtask_index (`int`) : index of the subtask to be bid on
        - main_measurement (`str`): name of the main measurement assigned by this subtask bid
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
        - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
        - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
    """
    def __init__(   self, 
                    req: dict, 
                    subtask_index: int, 
                    main_measurement: str, 
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = Bid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    dt_converge: Union[float, int] = 0, 
                    performed: bool = False
                ) -> object:
        """
        ### Arguments:
            - req (`dict`): measurement request being bid on
            - subtask_index (`int`) : index of the subtask to be bid on
            - main_measurement (`str`): name of the main measurement assigned by this subtask bid
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
            - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
            - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
        """
        super().__init__(   BidTypes.UNCONSTRAINED_BID.value,
                            req, 
                            subtask_index, 
                            main_measurement, 
                            bidder, 
                            winning_bid, 
                            own_bid, 
                            winner, 
                            t_img, 
                            t_update, 
                            dt_converge, 
                            performed
                            )
    
    def new_bids_from_request(task : MeasurementRequest, bidder : str) -> list:
        """
        Generates subtask bids from a measurement task request
        """
        subtasks = []        
        for subtask_index in range(len(task.measurement_groups)):
            main_measurement, dependent_measurements = task.measurement_groups[subtask_index]
            
            if len(dependent_measurements) > 0: 
                continue
            
            subtasks.append(UnconstrainedBid(   task.to_dict(), 
                                                subtask_index,
                                                main_measurement,
                                                bidder))
        return subtasks

class ConstrainedBid(Bid):
    """
    ## Unconstrained Bid

    Describes a bid placed on a measurement request that has temporal and coalition constraints

    ### Attributes:
        - req (`dict`): task being bid on
        - req_id (`str`): id of the task being bid on
        - subtask_index (`int`) : index of the subtask to be bid on
        - main_measurement (`str`): name of the main measurement assigned by this subtask bid
        - dependencies (`list`): portion of the dependency matrix related to this subtask bid
        - time_constraints (`list`): portion of the time dependency matrix related to this subtask bid
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
        - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
        - t_violation (`float` or `int`): time from which this task bid has been in violation of its constraints
        - dt_violoation (`float` or `int`): maximum time in which this bid is allowed to be in violation of its constraints
        - bid_solo (`int`): maximum number of solo bid attempts with no constraint satisfaction attempts
        - bid_any (`int`): maximum number of bid attempts with partial constraint satisfaction attempts
        - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
    """     
    def __init__(   self, 
                    req: dict, 
                    subtask_index: int, 
                    main_measurement: str, 
                    dependencies: list, 
                    time_constraints: list, 
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = Bid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    dt_converge: Union[float, int] = 0, 
                    t_violation: Union[float, int] = np.Inf, 
                    dt_violoation: Union[float, int] = 1e-6,
                    bid_solo : int = 1,
                    bid_any : int = 1, 
                    performed: bool = False
                ) -> object:
        """
        ### Arguments:
            - req (`dict`): task being bid on
            - subtask_index (`int`) : index of the subtask to be bid on
            - main_measurement (`str`): name of the main measurement assigned by this subtask bid
            - dependencies (`list`): portion of the dependency matrix related to this subtask bid
            - time_constraints (`list`): portion of the time dependency matrix related to this subtask bid
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
            - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
            - t_violation (`float` or `int`): time from which this task bid has been in violation of its constraints
            - dt_violoation (`float` or `int`): maximum time in which this bid is allowed to be in violation of its constraints
            - bid_solo (`int`): maximum number of solo bid attempts with no constraint satisfaction attempts
            - bid_any (`int`): maximum number of bid attempts with partial constraint satisfaction attempts
            - performed (`bool`): indicates if the winner of this bid has performed the measurement request at hand
        """     
        super().__init__(   BidTypes.CONSTRAINED_BID.value,
                            req, 
                            subtask_index, 
                            main_measurement, 
                            bidder, 
                            winning_bid, 
                            own_bid, 
                            winner, 
                            t_img, 
                            t_update, 
                            dt_converge, 
                            performed
                        )

        self.time_constraints = time_constraints
        self.dependencies = dependencies
        for dependency in dependencies:
            if dependency > 0:
                self.N_req += 1

        self.t_violation = t_violation
        self.dt_violation = dt_violoation
        
        if not isinstance(bid_solo, int):
            raise ValueError(f'`bid_solo` must be of type `int`. Is of type {type(bid_solo)}')
        elif bid_solo < 0:
            raise ValueError(f'`bid_solo` must be a positive `int`. Was given value of {bid_solo}.')
        self.bid_solo = bid_solo
        self.bid_solo_max = bid_solo

        if not isinstance(bid_any, int):
            raise ValueError(f'`bid_solo` must be of type `int`. Is of type {type(bid_any)}')
        elif bid_any < 0:
            raise ValueError(f'`bid_solo` must be a positive `int`. Was given value of {bid_any}.')
        self.bid_any = bid_any
        self.bid_any_max = bid_any
        self.dt_converge = dt_converge    

    def set_bid(self, new_bid: Union[int, float], t_img: Union[int, float], t_update: Union[int, float]) -> None:
        super().set_bid(new_bid, t_img, t_update)
        self.t_violation = t_update if 1 in self.time_constraints else np.Inf

    def __str__(self) -> str:
        return f"{super().__str__()},{round(self.t_violation, 3)},{self.bid_solo},{self.bid_any}"
    
    def reset_bid_counters(self) -> None:
        """
        Resets this bid's bid counters for optimistic bidding strategies when replanning
        """
        self.bid_solo = self.bid_solo_max
        self.bid_any = self.bid_any_max

    def new_bids_from_request(task : MeasurementRequest, bidder : str) -> list:
        """
        Generates subtask bids from a measurement task request
        """
        subtasks = []        
        for subtask_index in range(len(task.measurement_groups)):
            main_measurement, _ = task.measurement_groups[subtask_index]
            subtasks.append(ConstrainedBid( task.to_dict(), 
                                        subtask_index,
                                        main_measurement,
                                        task.dependency_matrix[subtask_index],
                                        task.time_dependency_matrix[subtask_index],
                                        bidder))
        return subtasks

    def reset(self, t_update: Union[float, int]) -> None:
        # reset bid values
        super().reset(t_update)        

        # reset violation timer
        self.__reset_violation_timer(t_update)

    def _update_info(self, 
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

        super()._update_info(other)
        self.t_update = t
        self.performed = other.performed
        self.t_violation = other.t_violation

    def __set_violation_timer(self, t : Union[int, float]) -> None:
        """
        Updates violation counter
        """
        self.t_violation = t 

    def __reset_violation_timer(self, t : Union[int, float]) -> None:
        """
        Resets violation counter
        """
        self.t_violation = np.Inf
        return

    def is_optimistic(self) -> bool:
        """
        Checks if bid has an optimistic bidding strategy
        """
        for dependency in self.dependencies:
            if dependency > 0:
                return True

        return False   

    def __has_timed_out(self, t : Union[int, float]) -> bool:
        """
        Returns True if the subtask's constraint violation timer has ran out.    
        """
        if self.t_violation == np.Inf:
            return False

        return t >= self.dt_violation + self.t_violation
    
    def count_coal_conts_satisied(self, others : list) -> int:
        """
        Counts the total number of satisfied coalition constraints
        """
        if len(others) != len(self.dependencies):
            raise ValueError(f'`others` list must be of length {len(self.dependencies)}. is of length {len(others)}')
        
        n_sat = 0
        for i in range(len(others)):
            other_bid : ConstrainedBid = others[i]
            if self.dependencies[i] == 1 and other_bid.winner != ConstrainedBid.NONE:
                n_sat += 1
        
        return n_sat 

    def check_constraints(self, others : list, t : Union[int, float]) -> tuple:
        """
        Compares current bid to other bids for the same task but different subtasks and checks for constraint satisfaction
        
        ### Arguments:
            - others (`list`): list of all subtasks bids from the same task
            -  (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): returns bid information to be rebroadcasted to other agents.
        """
        mutex_sat = self.__mutex_sat(others, t)
        dep_sat = self.__dep_sat(others, t)
        temp_sat, const_failed = self.__temp_sat(others, t)

        if not mutex_sat or not dep_sat or not temp_sat:
            if self.is_optimistic():
                self.bid_any -= 1
                self.bid_any = self.bid_any if self.bid_any > 0 else 0

                self.bid_solo -= 1
                self.bid_solo = self.bid_solo if self.bid_solo >= 0 else 0
            
            return self, const_failed

        return None, None

    def __mutex_sat(self, others : list, _ : Union[int, float]) -> bool:
        """
        Checks for mutually exclusive dependency satisfaction
        """
        # calculate total agent bid count
        agent_bid = self.winning_bid
        agent_coalition = [self.subtask_index]
        for bid_i in others:
            bid_i : ConstrainedBid
            bid_i_index = others.index(bid_i)

            if bid_i_index == self.subtask_index:
                continue

            if self.dependencies[bid_i_index] == 1:
                agent_bid += bid_i.winning_bid
                agent_coalition.append(bid_i_index)

        # initiate coalition bid count, find all possible coalitions
        task = MeasurementRequest.from_dict(self.req)
        possible_coalitions = []
        for i in range(len(task.dependency_matrix)):
            coalition = [i]
            for j in range(len(task.dependency_matrix[i])):
                if task.dependency_matrix[i][j] == 1:
                    coalition.append(j)
            possible_coalitions.append(coalition)
        
        # calculate total mutex bid count
        max_mutex_bid = 0
        for coalition in possible_coalitions:
            mutex_bid = 0
            for coalition_member in coalition:
                bid_i : ConstrainedBid = others[coalition_member]

                if self.subtask_index == coalition_member:
                    continue
                
                is_mutex = True
                for agent_coalition_member in agent_coalition:
                  if task.dependency_matrix[coalition_member][agent_coalition_member] >= 0:
                    is_mutex = False  
                    break

                if not is_mutex:
                    break
                
                mutex_bid += bid_i.winning_bid

            max_mutex_bid = max(mutex_bid, max_mutex_bid)

        return agent_bid > max_mutex_bid

    def __dep_sat(self, others : list, t : Union[int, float]) -> bool:
        """
        Checks for dependency constraint satisfaction
        """
        n_sat = self.count_coal_conts_satisied(others)
        if self.is_optimistic():
            if self.N_req > n_sat:
                self.__set_violation_timer(t)    
            else:
                self.__reset_violation_timer(t)
            return not self.__has_timed_out(t)
        else:
            return self.N_req == n_sat

    def __temp_sat(self, others : list, t : Union[int, float]) -> bool:
        """
        Checks for temporal constraint satisfaction
        """
        for other in others:
            other : ConstrainedBid
            if other.winner == ConstrainedBid.NONE:
                continue

            corr_time_met = (self.t_img <= other.t_img + self.time_constraints[other.subtask_index]
                            and other.t_img <= self.t_img + other.time_constraints[self.subtask_index])
            
            dependent = other.dependencies[self.subtask_index] > 0

            # tie_breaker = self.is_optimistic() and (self.t_img > other.t_img)

            # if not corr_time_met and not independent and not tie_breaker:
            if not corr_time_met and dependent:
                return False, other
        
        return True, None


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

class GreedyBid(Bid):
    """
    ## Bid for Greedy planner

    Describes a bid placed on a measurement request by a given agent

    ### Attributes:
        - req (`dict`): measurement request being bid on
        - req_id (`str`): id of the request being bid on
        - subtask_index (`int`) : index of the subtask to be bid on
        - main_measurement (`str`): name of the main measurement assigned by this subtask bid
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
    """
    def __init__(
                    self, 
                    req: dict, 
                    subtask_index : int,
                    main_measurement : str,
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = Bid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1,
                    **_
                ) -> Bid:
        """
        Creates an instance of a task bid

        ### Arguments:
            - req (`dict`): measurement request being bid on
            - main_measurement (`str`): name of the main measurement assigned by this subtask bid
            - dependencies (`list`): portion of the dependency matrix related to this subtask bid
            - time_constraints (`list`): portion of the time dependency matrix related to this subtask bid
            - bidder (`bidder`): name of the agent keeping track of this bid information
            - own_bid (`float` or `int`): latest bid from bidder
            - winner (`str`): name of current the winning agent
            - winning_bid (`float` or `int`): current winning bid
            - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        super().__init__(BidTypes.GREEDY.value, req, subtask_index, main_measurement, bidder, winning_bid, own_bid, winner, t_img, t_update)

        self.subtask_index = subtask_index
        self.main_measurement = main_measurement
        
    def set_bid(self, new_bid : Union[int, float], t_img : Union[int, float], t_update : Union[int, float]) -> None:
        """
        Sets new values for this bid

        ### Arguments: 
            - new_bid (`int` or `float`): new bid value
            - t_img (`int` or `float`): new imaging time
            - t_update (`int` or `float`): update time
        """
        self.own_bid = new_bid
        self.winning_bid = new_bid
        self.winner = self.bidder
        self.t_img = t_img
        self.t_update = t_update

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `subtask_index`, `main_measurement`, `dependencies`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`, `t_update`
        """
        task = MeasurementRequest(**self.req)
        split_id = task.id.split('-')
        line_data = [split_id[0], self.subtask_index, self.main_measurement, self.dependencies, task.pos, self.bidder, round(self.own_bid, 3), self.winner, round(self.winning_bid, 3), round(self.t_img, 3), round(self.t_violation, 3), self.bid_solo, self.bid_any]
        out = ""
        for i in range(len(line_data)):
            line_datum = line_data[i]
            out += str(line_datum)
            if i < len(line_data) - 1:
                out += ','

        return out
    
    def copy(self) -> object:
        return GreedyBid(  **self.to_dict() )

    def new_bids_from_request(req : MeasurementRequest, bidder : str) -> list:
        """
        Generates subtask bids from a measurement task request
        """
        subtasks = []        
        for subtask_index in range(len(req.measurement_groups)):
            main_measurement, dependend_measurements = req.measurement_groups[subtask_index]

            if len(dependend_measurements) == 0:
                # DO NOT allow for colaboration
                subtasks.append(GreedyBid(  
                                            req.to_dict(), 
                                            subtask_index,
                                            main_measurement,
                                            bidder
                                        )
                                )
        return subtasks

    def reset(self, t_update: Union[float, int]) -> None:        
        # reset bid values
        super().reset(t_update)

    def has_winner(self) -> bool:
        """
        Checks if this bid has a winner
        """
        return self.winner != GreedyBid.NONE

    def update(self, other_dict: dict, t_update: Union[float, int]) -> object:
        other = GreedyBid(**other_dict)

        if (    other.winning_bid > self.winning_bid
            or (other.winning_bid == self.winning_bid and self._tie_breaker(self, other))
            ):
            self._update_info(other)
            
        self.t_update = t_update
        return self

    def _update_info(self, other : Bid, t_update: Union[float, int]) -> None:
        super()._update_info(other)
        self.t_update = t_update
        

    def reset(self, t: Union[float, int]) -> None:
        super().reset()
        self.t_update = t
