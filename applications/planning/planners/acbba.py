"""
*********************************************************************************
    ___   __________  ____  ___       ____  __                           
   /   | / ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
  / /| |/ /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
 / ___ / /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
/_/  |_\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

import math

import numpy as np
from planners.planners import *
from messages import *
from states import SimulationAgentState
from tasks import *
from zmq import asyncio as azmq
from dmas.agents import AgentAction
from dmas.modules import *

class TaskBid(Bid):
    """
    ## Task Bid for ACBBA 

    Describes a bid placed on a task by a given agent

    ### Attributes:
        - task (`dict`): task being bid on
        - task_id (`str`): id of the task being bid on
        - bidder (`bidder`): name of the agent keeping track of this bid information
        - own_bid (`float` or `int`): latest bid from bidder
        - winner (`str`): name of current the winning agent
        - winning_bid (`float` or `int`): current winning bid
        - t_img (`float` or `int`): time where the task is set to be performed by the winning agent
        - t_update (`float` or `int`): latest time when this bid was updated
        - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
    """
    def __init__(self, 
                    task : dict, 
                    bidder : str,
                    winning_bid : Union[float, int] = 0, 
                    own_bid : Union[float, int] = 0, 
                    winner : str = Bid.NONE,
                    t_img : Union[float, int] = -1, 
                    t_update : Union[float, int] = -1,
                    dt_converge : Union[float, int] = 0.0,
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
            - t_update (`float` or `int`): latest time when this bid was updated
            - dt_converge (`float` or `int`): time interval after which local convergence is assumed to have been reached
        """
        super().__init__(task, bidder, winning_bid, own_bid, winner, t_img)
        self.t_update = t_update
        self.dt_converge = dt_converge

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`, `t_update`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_img},{self.t_update}'

    def update(self, other_dict : dict, t : Union[float, int]) -> object:
        """
        Compares bid with another and either updates, resets, or leaves the information contained in this bid
        depending on the rules specified in:
            - Whitten, Andrew K., et al. "Decentralized task allocation with coupled constraints in complex missions." Proceedings of the 2011 American Control Conference. IEEE, 2011.

        ### Arguments:
            - other_dict (`dict`): dictionary representing the bid being compared to
            - t (`float` or `dict`): time when this information is being updated

        ### Returns:
            - rebroadcast (`TaskBid` or `NoneType`): returns bid information to be rebroadcasted to other agents.
        """
        other : TaskBid = TaskBid(**other_dict)
        if self.task_id != other.task_id:
            # if update is for a different task, ignore update
            raise AttributeError(f'cannot update bid with information from another bid intended for another task (expected task id: {self.task_id}, given id: {other.task_id})')

        if other.bidder == self.bidder:
            if other.t_update > self.t_update:
                self._update_info(other,t)
            else:
                self._leave(t)
        
        elif other.winner is other.NONE:
            if self.winner == self.bidder:
                # leave and rebroadcast
                self._leave(t)
                return self

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other

            elif self.winner not in [self.bidder, other.bidder]:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

            elif self.winner == self.NONE:
                # leave and no rebroadcast
                self._leave(t)
                return self

        elif other.winner == other.bidder:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other
                    
                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other
                
                    # _, their_id = other.bidder.split('_')
                    # _, my_id = self.bidder.split('_')
                    # their_id = int(their_id); my_id = int(my_id)

                    # if their_id < my_id:
                    #     # update and rebroadcast
                    #     self._update_info(other, t)
                    #     return other

                if other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return self

            elif self.winner == other.bidder:
                if other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None

                elif other.t_update < self.t_update:
                    # leave and not rebroadcast
                    self._leave(t)
                    return None

            elif self.winner not in [self.bidder, other.bidder]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    #leave and rebroadcast
                    self._leave(t)
                    return self

                elif other.winning_bid == self.winning_bid:
                    # leave and rebroadcast
                    self._leave(t)
                    return self

                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other

        elif other.winner == self.bidder:
            if self.winner == self.bidder:
                if abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None
                
            elif self.winner == other.bidder:
                # reset and rebroadcast with current update time
                self.reset(t)
                return self

            elif self.winner not in [self.bidder, other.bidder]:
                # leave and rebroadcast
                self._leave(t)
                return self

            elif self.winner == self.NONE:
                # leave and rebroadcast with current update time
                self.__update_time(t)
                return self

        elif other.winner not in [self.bidder, other.bidder]:
            if self.winner == self.bidder:
                if other.winning_bid > self.winning_bid:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

                elif other.winning_bid == self.winning_bid:
                    # if there's a tie, bidder with the smallest id wins
                    if self._tie_breaker(other, self):
                        # update and rebroadcast
                        self._update_info(other, t)
                        return other
                    
                    # _, their_id = other.bidder.split('_')
                    # _, my_id = self.bidder.split('_')

                    # their_id = int(their_id); my_id = int(my_id)

                    # if their_id < my_id:
                    #     #update and rebroadcast
                    #     self._update_info(other, t)
                    #     return other

                elif other.winning_bid < self.winning_bid:
                    # update time and rebroadcast
                    self.__update_time(t)
                    return other

            elif self.winner == other.bidder:
                # update and rebroadcast
                self._update_info(other, t)
                return other

            elif self.winner == other.winner:
                if other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other
                    
                elif abs(other.t_update - self.t_update) < 1e-6:
                    # leave and no rebroadcast
                    self._leave(t)
                    return None

                elif other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self

            elif self.winner not in [self.bidder, other.bidder, other.winner]:
                if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other

                elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self
                    
                elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
                    # update and rebroadcast
                    self._update_info(other, t)
                    return other
                    
                elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
                    # leave and rebroadcast
                    self._leave(t)
                    return self

            elif self.winner == self.NONE:
                # update and rebroadcast
                self._update_info(other, t)
                return other
        
        return None
    
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
        self.__update_time(t)

    def __update_time(self, t_update : Union[float, int]) -> None:
        """
        Only updates the time since this bid was last updated

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        self.t_update = t_update

    def reset(self, t_update : Union[float, int]) -> None:
        """
        Resets the values of this bid while keeping track of lates update time

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """
        super().reset()
        self.t_update = t_update

    def _leave(self, t : Union[float, int]):
        """
        Leaves bid as is (used for algorithm readibility).

        ### Arguments:
            - t_update (`float` or `int`): latest time when this bid was updated
        """        
        return super()._leave()

    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        return TaskBid(self.task, self.bidder, self.winning_bid, self.winner, self.t_img, self.t_update)

class ACBBAPlannerModule(ConsensusPlanner):
    """
    # Asynchronous Consensus-Based Bundle Algorithm Planner
    """
    def __init__(
                self, 
                results_path: str,
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                l_bundle: int, 
                planner_type : PlannerTypes = PlannerTypes.ACBBA,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        """
        Creates an intance of an ACBBA Planner Module

        ### Arguments:
            - results_path (`str`): path for printing this planner's results
            - manager_port (`int`): localhost port used by the parent agent
            - agent_id (`int`): iddentification number for the parent agent
            - parent_network_config (:obj:`NetworkConfig`): network config of the parent agent
            - l_bundle (`int`): maximum bundle size
            - level (`int`): logging level
            - logger (`logging.Logger`): logger being used 
        """
        super().__init__(results_path, manager_port, agent_id, parent_network_config, planner_type, l_bundle, level, logger)
    
    async def setup(self) -> None:
        # initialize internal messaging queues
        self.states_inbox = asyncio.Queue()
        self.relevant_changes_inbox = asyncio.Queue()
        self.action_status_inbox = asyncio.Queue()

        self.outgoing_listen_inbox = asyncio.Queue()
        self.outgoing_bundle_builder_inbox = asyncio.Queue()

    async def live(self) -> None:
        """
        Performs three concurrent tasks:
        - Listener: receives messages from the parent agent and checks results
        - Bundle-builder: plans and bids according to local information
        - Rebroadcaster: forwards plan to agent
        """
        try:
            listener_task = asyncio.create_task(self.listener(), name='listener()')
            bundle_builder_task = asyncio.create_task(self.bundle_builder(), name='bundle_builder()')
            rebroadcaster_task = asyncio.create_task(self.rebroadcaster(), name='rebroadcaster()')
            
            tasks = [listener_task, bundle_builder_task, rebroadcaster_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        finally:
            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                if not task.done():
                    task.cancel()
                    await task

    async def listener(self):
        """
        ## Listener 

        Listen for any messages from the parent agent and adjust its results ledger.
        Any relevant bids that may affect the bundle, along with any changes in state or 
        task completion status are forwarded to the bundle builder.
        """
        # 
        try:
            # initiate results tracker
            results = {}
            t_curr = 0.0

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                    return

                elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!")

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)     

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                            # unpack message 
                            action_msg = AgentActionMessage(**sense)
                            self.log(f"received agent action of status {action_msg.status}! sending to bundle-builder...")
                            
                            # send to bundle builder 
                            await self.action_status_inbox.put(action_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                            # unpack message 
                            state_msg : AgentStateMessage = AgentStateMessage(**sense)
                            self.log(f"received agent state message! sending to bundle-builder...")
                            
                            # update current time:
                            state = SimulationAgentState(**state_msg.state)
                            if t_curr < state.t:
                                t_curr = state.t

                            # send to bundle builder 
                            await self.states_inbox.put(state_msg) 

                        elif sense['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                            # unpack message
                            task_req = TaskRequest(**sense)
                            task_dict : dict = task_req.task
                            task = MeasurementTask(**task_dict)

                            # check if task has already been received
                            if task.id in results:
                                self.log(f"received task request of an already registered task. Ignoring request...")
                                continue
                            
                            # create task bid from task request and add to results
                            self.log(f"received new task request! Adding to results ledger...")
                            bid = TaskBid(task_dict, self.get_parent_name())
                            results[task.id] = bid

                            # send to bundle-builder and rebroadcaster
                            out_msg = TaskBidMessage(   
                                                        self.get_element_name(), 
                                                        self.get_parent_name(), 
                                                        bid.to_dict()
                                                    )
                            await self.relevant_changes_inbox.put(out_msg)
                            await self.outgoing_listen_inbox.put(out_msg)

                        elif sense['msg_type'] == SimulationMessageTypes.TASK_BID.value:
                            # unpack message 
                            bid_msg : TaskBidMessage = TaskBidMessage(**sense)
                            their_bid = TaskBid(**bid_msg.bid)
                            self.log(f"received a bid from another agent for task {their_bid.task_id}!")
                            
                            await self.relevant_changes_inbox.put(bid_msg)

                else:
                    self.log(f"received manager broadcast or type {content['msg_type']}! ignoring...")
        
        except asyncio.CancelledError:
            return

        finally:
            self.listener_results = results

    async def bundle_builder(self) -> None:
        """
        ## Bundle-builder

        Performs periodic checks on the received messages from the listener and
        creates a plan based.
        """
        results = {}
        bundle = []
        path = []
        t_curr = 0.0
        t_next = 0.0
        f_update = 1.0
        plan = []
        converged = 0

        try:
            while True:
                # wait for next periodict check
                state_msg : AgentStateMessage = await self.states_inbox.get()
                state = SimulationAgentState(**state_msg.state)
                t_curr = state.t
                await self.update_current_time(t_curr)
                
                # TODO add fixed periodic checking of messages
                # if t_curr < t_next:
                #     # update threshold has not been reached yet; instruct agent to wait for messages
                #     action = WaitForMessages(t_curr, t_next)
                #     await self.outgoing_bundle_builder_inbox.put(action)
                #     continue

                # # set next update time
                # t_next += 1/f_update
                
                # if self.relevant_changes_inbox.empty():
                #     # if no relevant messages have been received by the update time; wait for next update time
                #     action = WaitForMessages(t_curr, t_next)
                #     await self.outgoing_bundle_builder_inbox.put(action)
                #     continue
                
                # t_update = t_curr

                # compare bids with incoming messages
                # self.log_results(results, 'INITIAL RESULTS', level=logging.WARNING)
                # self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                # self.log_task_sequence('path', path, level=logging.WARNING)
                
                changes = []
                while not self.relevant_changes_inbox.empty():
                    # get next bid
                    bid_msg : TaskBidMessage = await self.relevant_changes_inbox.get()
                    
                    # unpackage bid
                    their_bid = TaskBid(**bid_msg.bid)
                    
                    # check if bid exists for this task
                    new_task = their_bid.task_id not in results
                    if new_task:
                        # was not aware of this task; add to results as a blank bid
                        results[their_bid.task_id] = TaskBid( their_bid.task, self.get_parent_name())

                    # compare bids
                    my_bid : TaskBid = results[their_bid.task_id]
                    self.log(f'comparing bids...\nmine:  {my_bid}\ntheirs: {their_bid}', level=logging.DEBUG)
                    broadcast_bid : TaskBid = my_bid.update(their_bid.to_dict(), t_curr)
                    self.log(f'updated: {my_bid}\n', level=logging.DEBUG)
                    results[their_bid.task_id] = my_bid
                        
                    # if relevant changes were made, add to changes broadcast
                    if broadcast_bid or new_task:
                        broadcast_bid = broadcast_bid if not new_task else my_bid
                        out_msg = TaskBidMessage(   
                                                self.get_parent_name(), 
                                                self.get_parent_name(), 
                                                broadcast_bid.to_dict()
                                            )
                        changes.append(out_msg)
                    
                    # if outbid for a task in the bundle, release subsequent tasks in bundle and path
                    bid_task = MeasurementTask(**my_bid.task)
                    if bid_task in bundle and my_bid.winner != self.get_parent_name():
                        bid_index = bundle.index(bid_task)

                        for _ in range(bid_index, len(bundle)):
                            # remove task from bundle
                            measurement_task : MeasurementTask = bundle.pop(bid_index)
                            path.remove(measurement_task)

                            # if the agent is currently winning this bid, reset results
                            current_bid : TaskBid = results[measurement_task.id]
                            if current_bid.winner == self.get_parent_name():
                                current_bid.reset(t_curr)
                                results[measurement_task.id] = current_bid

                            # self.log_results(results, 'PRELIMIANARY COMPARED RESULTS', level=logging.WARNING)
                            # self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                            # self.log_task_sequence('path', path, level=logging.WARNING)

                # release tasks from bundle if t_end has passed
                task_to_remove = None
                for task in bundle:
                    task : MeasurementTask
                    if task.t_end - task.duration < t_curr:
                        task_to_remove = task
                        break

                if task_to_remove is not None:
                    bid_index = bundle.index(task_to_remove)

                    for _ in range(bid_index, len(bundle)):
                        # remove task from bundle
                        measurement_task = bundle.pop(bid_index)
                        path.remove(measurement_task)

                # update bundle from new information
                # self.log_results(results, 'COMPARED RESULTS', level=logging.WARNING)
                # self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                # self.log_task_sequence('path', path, level=logging.WARNING)

                available_tasks : list = self.get_available_tasks(state, bundle, results)

                changes_to_bundle = []
                current_bids = {task.id : results[task.id] for task in bundle}
                max_path = [task for task in path]; 
                max_path_bids = {task.id : results[task.id] for task in path}
                max_path_utility = self.sum_path_utility(path, current_bids)

                while len(bundle) < self.l_bundle and len(available_tasks) > 0:                   
                    # find next best task to put in bundle (greedy)
                    max_task = None; 
                    for measurement_task in available_tasks:
                        # calculate bid for a given available task
                        measurement_task : MeasurementTask
                        projected_path, projected_bids, projected_path_utility = self.calc_path_bid(state, path, measurement_task)
                        
                        # check if path was found
                        if projected_path is None:
                            continue

                        # compare to maximum task
                        if (max_task is None or projected_path_utility > max_path_utility):

                            # all bids must out-bid the current winners
                            outbids_all = True 
                            for projected_task in projected_path:
                                projected_task : MeasurementTask
                                proposed_bid : TaskBid = projected_bids[projected_task.id]
                                current_bid : TaskBid = results[projected_task.id]

                                if current_bid > proposed_bid:
                                    # ignore path if proposed bid for any task cannot out-bid current winners
                                    outbids_all = False
                                    break
                            
                            if not outbids_all:
                                continue
                            
                            max_path = projected_path
                            max_task = measurement_task
                            max_path_bids = projected_bids
                            max_path_utility = projected_path_utility

                    if max_task is not None:
                        # max bid found! place task with the best bid in the bundle and the path
                        bundle.append(max_task)
                        path = max_path

                        # remove bid task from list of available tasks
                        available_tasks.remove(max_task)

                        # self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                        # self.log_task_sequence('path', path, level=logging.WARNING)

                    else:
                        # no max bid was found; no more tasks can be added to the bundle
                        break

                #  update bids
                for measurement_task in path:
                    measurement_task : MeasurementTask
                    new_bid : TaskBid = max_path_bids[measurement_task.id]
                    
                    if results[measurement_task.id] != new_bid:
                        changes_to_bundle.append(measurement_task)

                    results[measurement_task.id] = new_bid

                # broadcast changes to bundle
                for measurement_task in changes_to_bundle:
                    measurement_task : MeasurementTask

                    new_bid = results[measurement_task.id]

                    # add to changes broadcast
                    out_msg = TaskBidMessage(   
                                            self.get_parent_name(), 
                                            self.get_parent_name(), 
                                            new_bid.to_dict()
                                        )
                    changes.append(out_msg)


                # self.log_results(results, 'MODIFIED BUNDLE RESULTS', level=logging.WARNING)
                # self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                # self.log_task_sequence('path', path, level=logging.WARNING)

                # give agent tasks to perform at the current time
                actions = []
                if (len(changes) == 0 
                    and len(path) > 0
                    and self.check_path_constraints(path, results, t_curr)):

                    if converged < 1:
                        converged += 1

                        for measurement_task in bundle:
                            measurement_task : MeasurementTask

                            new_bid = results[measurement_task.id]

                            # add to changes broadcast
                            out_msg = TaskBidMessage(   
                                                    self.get_parent_name(), 
                                                    self.get_parent_name(), 
                                                    new_bid.to_dict()
                                                )
                            changes.append(out_msg)

                    elif len(plan) == 0:
                        # no plan has been generated yet; generate one
                        for i in range(len(path)):
                            measurement_task : MeasurementTask = path[i]
                            
                            if len(plan) == 0:
                                t_start = t_curr
                            else:
                                i_prev = (i-1)*2
                                prev_move : MoveAction = plan[i_prev]
                                prev_measure : MeasurementTask = plan[i_prev + 1]
                                t_start = prev_move.t_end + prev_measure.duration

                            task_pos = measurement_task.pos
                            agent_pos = state.pos

                            dx = np.sqrt( (task_pos[0] - agent_pos[0])**2 + (task_pos[1] - agent_pos[1])**2 )
                            t_end = t_start + dx / state.v_max

                            if isinstance(self._clock_config, FixedTimesStepClockConfig):
                                dt = self._clock_config.dt
                                prev_t_start = t_start
                                prev_t_end = t_end
                                if t_start < np.Inf:
                                    t_start = dt * math.floor(t_start/dt)
                                if t_end < np.Inf:
                                    t_end = dt * math.ceil(t_end/dt)

                                if t_end > t_start:
                                    t_end += dt

                            move_task = MoveAction(measurement_task.pos, t_start, t_end)

                            # plan per measurement request: move to plan, perform measurement 
                            plan.append(move_task)
                            plan.append(measurement_task)  

                        actions.append(plan[0])

                    else:
                        # plan has already been developed and is being performed; check plan complation status
                        while not self.action_status_inbox.empty():
                            action_msg : AgentActionMessage = await self.action_status_inbox.get()
                            performed_action = AgentAction(**action_msg.action)

                            latest_plan_action : AgentAction = plan[0]
                            if performed_action.id != latest_plan_action.id:
                                # some other task was performed; ignoring 
                                continue

                            elif performed_action.status == AgentAction.PENDING:
                                # latest action from plan was attepted but not completed; performing again
                                
                                if t_curr < latest_plan_action.t_start:
                                    # if action was not ready to be performed, wait for a bit
                                    actions.append( WaitForMessages(t_curr, latest_plan_action.t_start - t_curr) )
                                else:
                                    # try to perform action again
                                    actions.append(plan[0])

                            elif performed_action.status == AgentAction.COMPLETED or performed_action.status == AgentAction.ABORTED:
                                # latest action from plan was completed! performing next action in plan
                                done_task : AgentAction = plan.pop(0)
                                
                                if done_task in path:
                                    path.remove(done_task)
                                    bundle.remove(done_task)

                                if len(plan) > 0:
                                    next_task : AgentAction = plan[0]
                                    if t_curr >= next_task.t_start:
                                        actions.append(next_task)
                                    else:
                                        actions.append( WaitForMessages(t_curr, next_task.t_start) )
                        
                        if len(actions) == 0 and len(plan) > 0:
                            next_task : AgentAction = plan[0]
                            if t_curr >= next_task.t_start:
                                actions.append(next_task)
                            else:
                                actions.append( WaitForMessages(t_curr, next_task.t_start) )

                else:
                    # bundle is empty or cannot be executed yet; instructing agent to idle
                    plan = []
                    converged = 0
                    actions.append(WaitForMessages(t_curr, t_curr + 1/f_update))

                # send changes to rebroadcaster
                # for change in changes:
                #     await self.outgoing_bundle_builder_inbox.put(change)
                    
                # send actions to broadcaster
                if len(actions) == 0 and len(changes) == 0:
                    actions.append( WaitForMessages(t_curr, t_curr + 1/f_update) )
                # for action in actions:
                #     await self.outgoing_bundle_builder_inbox.put(action)

                change_dicts = [change.to_dict() for change in changes]
                action_dicts = [action.to_dict() for action in actions]
                action_dicts.extend(change_dicts)
                action_bus = BusMessage(self.get_element_name(), self.get_element_name(), action_dicts)
                await self.outgoing_bundle_builder_inbox.put(action_bus)
                
        except asyncio.CancelledError:
            return

        finally:
            self.bundle_builder_results = results

    def calc_utility(self, task : MeasurementTask, t_img : float) -> float:
        """
        Calculates the expected utility of performing a measurement task

        ### Arguments:
            - task (obj:`MeasurementTask`) task to be performed 
            - t_img (`float`): time at which the task will be performed

        ### Retrurns:
            - utility (`float`): estimated normalized utility 
        """
        # check time constraints
        if t_img < task.t_start or task.t_end < t_img:
            return 0.0
        
        # calculate urgency factor from task
        return task.s_max * np.exp( - task.urgency * (t_img - task.t_start) )

    def check_path_constraints(self, path : list, results : dict, t_curr : Union[float, int]) -> bool:
        """
        Checks if the bids of every task in the current path have all of their constraints
        satisfied by other bids.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        for task in path:
            # check constraints
            task : MeasurementTask
            if not self.check_task_constraints(task, results):
                return False
            
            # check local convergence
            my_bid : TaskBid = results[task.id]
            if t_curr < my_bid.t_update + my_bid.dt_converge:
                return False

        return True

    def check_task_constraints(self, task : MeasurementTask, results : dict) -> bool:
        """
        Checks if the bids in the current results satisfy the constraints of a given task.

        ### Returns:
            - True if all constraints are met; False otherwise
        """
        # TODO add bid and time constraints
        return True

    def can_bid(self, state : SimulationAgentState, task : MeasurementTask) -> bool:
        """
        Checks if an agent can perform a measurement task
        """
        # check capabilities - TODO: Replace with knowledge graph
        for instrument in task.measurements:
            if instrument not in state.instruments:
                return False

        # check time constraints
        ## Constraint 1: task must be able to be performed during or after the current time
        if task.t_end < state.t:
            return False
        
        return True

    def calc_path_bid(self, state : SimulationAgentState, original_path : list, task : MeasurementTask) -> tuple:
        winning_path = None
        winning_bids = None
        winning_path_utility = 0.0

        # find best placement in path
        for i in range(len(original_path)+1):
            # generate possible path
            path = [scheduled_task for scheduled_task in original_path]
            path.insert(i, task)

            # calculate bids for each task in the path
            bids = {}
            for task_i in path:
                # calculate arrival time
                task_i : MeasurementTask
                t_arrive = self.calc_imaging_time(state, path, bids, task_i)

                # calculate bidding score
                utility = self.calc_utility(task, t_arrive)

                # create bid
                bid = TaskBid(  
                                task_i.to_dict(), 
                                self.get_parent_name(),
                                utility,
                                utility,
                                self.get_parent_name(),
                                t_arrive,
                                state.t
                            )
                
                bids[task_i.id] = bid

            # look for path with the best utility
            path_utility = self.sum_path_utility(path, bids)
            if path_utility > winning_path_utility:
                winning_path = path
                winning_bids = bids
                winning_path_utility = path_utility

        return winning_path, winning_bids, winning_path_utility

    async def rebroadcaster(self) -> None:
        """
        ## Rebroadcaster

        Sends out-going mesasges from the bundle-builder and the listener to the parent agent.
        """
        try:
            while True:
                # wait for bundle-builder to finish processing information
                self.log('waiting for bundle-builder...')
                bundle_msgs = []
                bundle_bus : BusMessage = await self.outgoing_bundle_builder_inbox.get()
                for msg_dict in bundle_bus.contents:
                    msg_dict : dict
                    action_type = msg_dict.get('action_type', None)
                    msg_type = msg_dict.get('msg_type', None)
                    if action_type is not None:
                        bundle_msgs.append(action_from_dict(**msg_dict))
                    elif msg_type is not None:
                        bundle_msgs.append(message_from_dict(**msg_dict))

                self.log('bundle-builder sent its messages! comparing bids with listener...')

                # get all messages from listener                
                listener_msgs = []
                while not self.outgoing_listen_inbox.empty():
                    listener_msgs.append(await self.outgoing_listen_inbox.get())

                # compare and classify messages
                bid_messages = {}
                actions = []

                for msg in listener_msgs:
                    if isinstance(msg, TaskBidMessage):
                        listener_bid : TaskBid = TaskBid(**msg.bid)
                        bid_messages[listener_bid.task_id] = msg

                for msg in bundle_msgs:
                    if isinstance(msg, TaskBidMessage):
                        bundle_bid : TaskBid = TaskBid(**msg.bid)
                        if bundle_bid.task_id not in bid_messages:
                            bid_messages[bundle_bid.task_id] = msg
                        else:
                            # only keep most recent information for bids
                            listener_bid_msg : TaskBidMessage = bid_messages[bundle_bid.task_id]
                            listener_bid : TaskBid = TaskBid(**listener_bid_msg.bid)
                            if bundle_bid.t_update >= listener_bid.t_update:
                                bid_messages[bundle_bid.task_id] = msg
                            
                    elif isinstance(msg, AgentAction):
                        actions.append(msg)                        
        
                # build plan
                plan = []
                for bid_id in bid_messages:
                    bid_message : TaskBidMessage = bid_messages[bid_id]
                    plan.append(BroadcastMessageAction(bid_message.to_dict()).to_dict())

                for action in actions:
                    action : AgentAction
                    plan.append(action.to_dict())
                
                # send to agent
                self.log(f'bids compared! generating plan with {len(bid_messages)} bid messages and {len(actions)} actions')
                plan_msg = PlanMessage(self.get_element_name(), self.get_parent_name(), plan)
                await self._send_manager_msg(plan_msg, zmq.PUB)
                self.log(f'actions sent!')

        except asyncio.CancelledError:
            pass

    async def teardown(self) -> None:
        # print listener bidding results
        with open(f"{self.results_path}/{self.get_parent_name()}/listener_bids.csv", "w") as file:
            title = "task_id,bidder,own_bid,winner,winning_bid,t_img,t_update"
            file.write(title)

            for task_id in self.listener_results:
                bid : TaskBid = self.listener_results[task_id]
                file.write('\n' + str(bid))

        # print bundle-builder bidding results
        with open(f"{self.results_path}/{self.get_parent_name()}/bundle_builder_bids.csv", "w") as file:
            title = "task_id,bidder,own_bid,winner,winning_bid,t_img,t_update"
            file.write(title)

            for task_id in self.bundle_builder_results:
                bid : TaskBid = self.bundle_builder_results[task_id]
                file.write('\n' + str(bid))