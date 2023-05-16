"""
*********************************************************************************
    ___   ________________  ____  ___       ____  __                           
   /   | / ____/ ____/ __ )/ __ )/   |     / __ \/ /___ _____  ____  ___  _____
  / /| |/ /   / /   / __  / __  / /| |    / /_/ / / __ `/ __ \/ __ \/ _ \/ ___/
 / ___ / /___/ /___/ /_/ / /_/ / ___ |   / ____/ / /_/ / / / / / / /  __/ /    
/_/  |_\____/\____/_____/_____/_/  |_|  /_/   /_/\__,_/_/ /_/_/ /_/\___/_/     
                                                                         
*********************************************************************************
"""

import copy
from itertools import combinations, permutations
import logging
from typing import Union
import numpy as np

from tasks import *
from messages import *

from planners.planners import *
from planners.acbba import ACBBAPlannerModule
from planners.acbba import TaskBid

from dmas.agents import AgentAction
from dmas.messages import ManagerMessageTypes
from dmas.network import NetworkConfig

class SubtaskBid(TaskBid):
    def __init__(
                    self, 
                    task: dict, 
                    subtask_index : int,
                    main_measurement : str,
                    dependencies : list,
                    bidder: str, 
                    winning_bid: Union[float, int] = 0, 
                    own_bid: Union[float, int] = 0, 
                    winner: str = TaskBid.NONE, 
                    t_img: Union[float, int] = -1, 
                    t_update: Union[float, int] = -1, 
                    t_violation: Union[float, int] = -1, 
                    dt_violoation: Union[float, int] = 0, 
                    dt_converge: Union[float, int] = 0, 
                    **_
                ) -> object:
        super().__init__(task, bidder, winning_bid, own_bid, winner, t_img, t_update, dt_converge, **_)

        self.subtask_index = subtask_index
        self.main_measurement = main_measurement
        self.dependencies = TaskBid.NONE

        self.dependencies = dependencies
        self.time_constraints = []
        parent_task = MeasurementTask(**self.task)
        for dependency in dependencies:
            if -1 <= dependency <= 1:
                if dependency == 1:
                    self.time_constraints.append(parent_task.t_corr)
                else:
                    self.time_constraints.append(np.Inf)
            else:
                raise ValueError('Dependency vector must cuntain integers between [-1, 1]. ')

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `subtask_index`, `main_measurement`, `dependencies`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_img`, `t_update`
        """
        return f'{self.task_id},{self.subtask_index},{self.main_measurement},{self.dependencies},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_img},{self.t_update}'

    def copy(self) -> object:
        return SubtaskBid(  self.task, 
                            self.subtask_index,
                            self.dependencies,
                            self.bidder,
                            self.winning_bid,
                            self.own_bid,
                            self.winner,
                            self.t_img,
                            self.t_update,
                            self.dt_converge
                        )

    def has_winner(self) -> bool:
        """
        Checks if this bid has a winner
        """
        return self.winner != TaskBid.NONE

    def subtasks_from_task(task : MeasurementTask, bidder : str) -> list:
        """
        Generates subtask bids from a measurement task request
        """
        n_instruments = len(task.instruments)
        subtasks = []

        # create measurement groups
        measurement_groups = []
        for r in range(1, n_instruments+1):
            # combs = list(permutations(task_types, r))
            combs = list(combinations(task.instruments, r))
            
            for comb in combs:
                measurements = list(comb)
                main_measurement_permutations = list(permutations(comb, 1))
                for main_measurement in main_measurement_permutations:
                    main_measurement = list(main_measurement).pop()

                    dependend_measurements = copy.deepcopy(measurements)
                    dependend_measurements.remove(main_measurement)

                    if len(dependend_measurements) > 0:
                        measurement_groups.append((main_measurement, dependend_measurements))
                    else:
                        measurement_groups.append((main_measurement, []))
        
        # create dependency matrix
        dependency_matrix = np.zeros((len(measurement_groups), len(measurement_groups)))
        for index_a in range(len(measurement_groups)):
            main_a, dependents_a = measurement_groups[index_a]

            for index_b in range(index_a, len(measurement_groups)):
                main_b, dependents_b = measurement_groups[index_b]

                if index_a == index_b:
                    continue

                if len(dependents_a) != len(dependents_b):
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                elif main_a not in dependents_b or main_b not in dependents_a:
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                elif main_a == main_b:
                    dependency_matrix[index_a][index_b] = -1
                    dependency_matrix[index_b][index_a] = -1
                else:
                    dependents_a_extended : list = copy.deepcopy(dependents_a)
                    dependents_a_extended.remove(main_b)
                    dependents_b_extended : list = copy.deepcopy(dependents_b)
                    dependents_b_extended.remove(main_a)

                    if dependents_a_extended == dependents_b_extended:
                        dependency_matrix[index_a][index_b] = 1
                        dependency_matrix[index_b][index_a] = 1
                    else:
                        dependency_matrix[index_a][index_b] = -1
                        dependency_matrix[index_b][index_a] = -1

        # create subtasks
        for subtask_index in range(len(measurement_groups)):
            main_measurement, _ = measurement_groups[subtask_index]
            subtasks.append(SubtaskBid( task.to_dict(), 
                                        subtask_index,
                                        main_measurement,
                                        dependency_matrix[subtask_index],
                                        bidder))
        return subtasks

class ACCBBAPlannerModule(ACBBAPlannerModule):
    """
    # Asynchronous Consensus Constraint-Based Bundle Algorithm Planner
    """
    def __init__(   self, 
                    results_path: str, 
                    manager_port: int, 
                    agent_id: int, 
                    parent_network_config: NetworkConfig, 
                    l_bundle: int, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:
        """
        Creates an intance of an ACCBBA Planner Module

        ### Arguments:
            - results_path (`str`): path for printing this planner's results
            - manager_port (`int`): localhost port used by the parent agent
            - agent_id (`int`): iddentification number for the parent agent
            - parent_network_config (:obj:`NetworkConfig`): network config of the parent agent
            - l_bundle (`int`): maximum bundle size
            - level (`int`): logging level
            - logger (`logging.Logger`): logger being used 
        """
        super().__init__(results_path, manager_port, agent_id, parent_network_config, l_bundle, PlannerTypes.ACCBBA, level, logger)
        self.planner_type = PlannerTypes.ACCBBA

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

                            bids = SubtaskBid.subtasks_from_task(task, self.get_parent_name())
                            results[task.id] = bids

                            # send to bundle-builder and rebroadcaster
                            for bid in bids:
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
                            
                            their_bid = SubtaskBid(**bid_msg.bid)
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
                self.log_results('INITIAL RESULTS', results, level=logging.WARNING)
                self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                self.log_task_sequence('path', path, level=logging.WARNING)
                
                changes = []
                results, bundle, path, comp_changes = await self.compare_results(results, bundle, path, t_curr)
                changes.extend(comp_changes)

                self.log_results('COMPARED RESULTS', results, level=logging.WARNING)
                self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                self.log_task_sequence('path', path, level=logging.WARNING)
                
                # Check constraints
                results, bundle, path, cons_changes = await self.check_results_constraints(results, bundle, path, t_curr)
                changes.extend(cons_changes)

                self.log_results('CONSTRAINT CHECKED RESULTS', results, level=logging.WARNING)
                self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                self.log_task_sequence('path', path, level=logging.WARNING)

                # update bundle from new information
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

    async def compare_results(self, results : dict, bundle : list, path : list, t_curr : Union[int, float]) -> tuple:
        """
        Compares the existing results with any incoming task bids and updates the bundle accordingly

        ### Returns
            - results
            - bundle
            - path
            - changes
        """
        changes = []
        while not self.relevant_changes_inbox.empty():
            # get next bid
            bid_msg : TaskBidMessage = await self.relevant_changes_inbox.get()
            
            # unpackage bid
            their_bid = SubtaskBid(**bid_msg.bid)
            
            # check if bid exists for this task
            new_task = their_bid.task_id not in results
            if new_task:
                # was not aware of this task; add to results as a blank bid
                task = MeasurementTask(**their_bid.task)
                results[their_bid.task_id] = SubtaskBid.subtasks_from_task(task, self.get_parent_name())

            # compare bids
            my_bid : SubtaskBid = results[their_bid.task_id][their_bid.subtask_index]
            self.log(f'comparing bids...\nmine:  {my_bid}\ntheirs: {their_bid}', level=logging.DEBUG)
            broadcast_bid : SubtaskBid = my_bid.update(their_bid.to_dict(), t_curr)
            self.log(f'updated: {my_bid}\n', level=logging.DEBUG)
            results[their_bid.task_id][their_bid.subtask_index] = my_bid
                
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
            if (bid_task, my_bid.subtask_index) in bundle and my_bid.winner != self.get_parent_name():
                bid_index = bundle.index((bid_task, my_bid.subtask_index))

                for _ in range(bid_index, len(bundle)):
                    # remove all subsequent tasks from bundle
                    measurement_task, subtask_index = bundle.pop(bid_index)
                    path.remove((measurement_task, subtask_index))

                    # if the agent is currently winning this bid, reset results
                    current_bid : SubtaskBid = results[measurement_task.id][subtask_index]
                    if current_bid.winner == self.get_parent_name():
                        current_bid.reset(t_curr)
                        results[measurement_task.id][subtask_index] = current_bid

                    self.log_results('PRELIMIANARY COMPARED RESULTS', results, level=logging.WARNING)
                    self.log_task_sequence('bundle', bundle, level=logging.WARNING)
                    self.log_task_sequence('path', path, level=logging.WARNING)

        # release tasks from bundle if t_end has passed
        task_to_remove = None
        for task, subtask_index in bundle:
            task : MeasurementTask
            if task.t_end - task.duration < t_curr:
                task_to_remove = (task, subtask_index)
                break

        if task_to_remove is not None:
            bid_index = bundle.index(task_to_remove)

            for _ in range(bid_index, len(bundle)):
                # remove task from bundle
                measurement_task = bundle.pop(bid_index)
                path.remove(measurement_task)

        return results, bundle, path, changes


    async def check_results_constraints(self, results : dict, bundle : list, path : list, t_curr : Union[int, float]) -> tuple:
        changes = []
        # TODO Check if constraints are met for all subtasks with bids
        in_violation = []
        for task_id in results:
            subtask_bids : list = results[task_id]
            for subtask_bid in results[task_id]:
                subtask_bid : SubtaskBid
                for dep_constraint in subtask_bid.dependencies:
                    dep_bid : SubtaskBid = subtask_bids[dep_constraint]

                    if dep_constraint == 1:
                        # check assignment constraints
                        if not dep_bid.has_winner():
                            
                            pass

                        # check time constraints
                        else:
                            pass 

                    elif dep_constraint == 0:
                        continue
                     
                    elif dep_constraint == -1:
                        # check assignment constraints
                        if not dep_bid.has_winner():
                            
                            pass               


        # TODO reset bids and release tasks from bundle if t_violation exceeds tolerance

        return results, bundle, path, changes

    def get_available_tasks(self, state : SimulationAgentState, bundle : list, results : dict) -> list:
        """
        Checks if there are any tasks available to be performed

        ### Returns:
            - list containing all available and bidable tasks to be performed by the parent agent
        """
        available = []
        for task_id in results:
            for subtaskbid in results[task_id]:
                subtaskbid : SubtaskBid
                task = MeasurementTask(**subtaskbid.task)

                if self.can_bid(state, task, subtaskbid) and (task, subtaskbid.subtask_index) not in bundle and (subtaskbid.t_img >= state.t or subtaskbid.t_img < 0):
                    available.append((task, subtaskbid.subtask_index))

        return available

    def can_bid(self, state : SimulationAgentState, task : MeasurementTask, subtaskbid : SubtaskBid) -> bool:
        """
        Checks if an agent can perform a measurement task
        """
        # check capabilities - TODO: Replace with knowledge graph
        if subtaskbid.main_measurement not in state.instruments:
            return False 

        # check time constraints
        ## Constraint 1: task must be able to be performed during or after the current time
        if task.t_end < state.t:
            return False
        
        return True
        
    def log_results(self, dsc : str, results : dict, level=logging.DEBUG) -> None:
        """
        Logs current results at a given time for debugging purposes

        ### Argumnents:
            - dsc (`str`): description of what is to be logged
            - results (`dict`): results to be logged
            - level (`int`): logging level to be used
        """
        out = f'\n{dsc}\ntask_id,  i, mmt,\tdeps,\t\t   location,  bidder, bid, winner, winning_bid, t_img\n'
        for task_id in results:
            for bid in results[task_id]:
                bid : SubtaskBid
                task = MeasurementTask(**bid.task)
                split_id = task.id.split('-')
                out += f'{split_id[0]}, {bid.subtask_index}, {bid.main_measurement},\t{bid.dependencies}, {task.pos}, {bid.bidder}, {round(bid.own_bid, 3)}, {bid.winner}, {round(bid.winning_bid, 3)}, {round(bid.t_img, 3)}\n'

        self.log(out, level)