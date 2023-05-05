import copy
import math

import numpy as np
from messages import *
from states import SimulationAgentState
from tasks import *
from zmq import asyncio as azmq
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
        
        if self.parent_id < 1:
            msg_task = WaitForMessages(0, 3)
        else:
            msg_task = BroadcastStateAction(1, 2)

        self.plan = [
                    travel_to_target,
                    measure,
                    return_to_origin
                    # msg_task
                    ]
        
    async def live(self) -> None:
        try:
            work_task = asyncio.create_task(self.routine())
            listen_task = asyncio.create_task(self.listen())
            tasks = [work_task, listen_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        finally:
            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            for task in pending:
                task : asyncio.Task
                if not task.done():
                    task.cancel()
                    await task

    async def listen(self):
        """
        Listens for any incoming broadcasts and classifies them in their respective inbox
        """
        try:
            # create poller for all broadcast sockets
            poller = azmq.Poller()

            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)

            poller.register(manager_socket, zmq.POLLIN)

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                sockets = dict(await poller.poll())

                if manager_socket in sockets:
                    self.log('listening to manager broadcast!')
                    dst, src, content = await self.listen_manager_broadcast()

                    # if sim-end message, end agent `live()`
                    if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                        self.log(f"received manager broadcast of type {content['msg_type']}! terminating `live()`...")
                        return

                    # else, let agent handle it
                    else:
                        self.log(f"received manager broadcast of type {content['msg_type']}! sending to inbox...")
                        await self.manager_inbox.put( (dst, src, content) )

        except asyncio.CancelledError:
            return  
    
    async def routine(self) -> None:
        try:
            self.log('initial plan sent!')
            t_curr = 0
            while True:
                # listen for agent to send new senses
                self.log('waiting for incoming senses from parent agent...')
                sense_msgs = await self.empty_manager_inbox()

                senses = []
                for sense_msg_dict in sense_msgs:
                    if sense_msg_dict['msg_type'] == SimulationMessageTypes.SENSES.value:
                        sense_msg : SensesMessage = SensesMessage(**sense_msg_dict)
                        senses.append(sense_msg.state)
                        senses.extend(sense_msg.senses)                     

                self.log(f'received {len(senses)} senses from agent! processing senses...')
                new_plan = []
                for sense in senses:
                    sense : dict
                    if sense['msg_type'] == SimulationMessageTypes.AGENT_ACTION.value:
                        # unpack message 
                        msg = AgentActionMessage(**sense)
                        
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

class TaskBid(object):
    """
    ## Task Bid for ACCBBA 

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

    def __str__(self) -> str:
        """
        Returns a string representation of this task bid in the following format:
        - `task_id`, `bidder`, `own_bid`, `winner`, `winning_bid`, `t_arrive`, `t_update`
        """
        return f'{self.task_id},{self.bidder},{self.own_bid},{self.winner},{self.winning_bid},{self.t_arrive},{self.t_update}'

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
                    self.__leave(t)
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
                    self.__update_time(t)
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

        other : TaskBid
        self.winning_bid = other.winning_bid
        self.winner = other.winner
        self.t_arrive = other.t_arrive
        self.t_update = t
        if self.bidder == other.bidder:
            self.own_bid = other.own_bid

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
    
    # TODO: add comparison methods for easier bundle creation
    # def __lt__(self, other : object) -> bool:
    #     other : TaskBid
    #     if self.task_id != other.task_id:
    #         # if update is for a different task, ignore update
    #         raise AttributeError(f'cannot compare bidsintended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
    #     if other.winner == other.bidder:
    #         if self.winner == self.bidder:
    #             if other.winning_bid > self.winning_bid:
    #                 # outbid
    #                 return True
                    
    #             elif other.winning_bid == self.winning_bid:
    #                 # if there's a tie, bidder with the smallest id wins
    #                 _, their_id = other.bidder.split('_')
    #                 _, my_id = self.bidder.split('_')
    #                 their_id = int(their_id); my_id = int(my_id)

    #                 if their_id < my_id:
    #                     # outbid
    #                     return True

    #             if other.winning_bid < self.winning_bid:
    #                 # NOT outbid
    #                 return False

    #         elif self.winner == other.bidder:
    #             if other.t_update > self.t_update:
    #                 if other.winning_bid > self.winning_bid:
    #                     # outbid 
    #                     return True

    #             elif abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass

    #             elif other.t_update < self.t_update:
    #                 # leave and not rebroadcast
    #                 pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
    #                 #leave and rebroadcast
    #                 pass

    #             elif other.winning_bid == self.winning_bid:
    #                 # leave and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # update and rebroadcast
    #             pass

    #     elif other.winner == self.bidder:
    #         if self.winner == self.bidder:
    #             if abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass
                
    #         elif self.winner == other.bidder:
    #             # reset and rebroadcast with current update time
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             # leave and rebroadcast
    #             pass

    #         elif self.winner == self.NONE:
    #             # leave and rebroadcast with current update time
    #             pass

    #     elif other.winner not in [self.bidder, other.bidder]:
    #         if self.winner == self.bidder:
    #             if other.winning_bid > self.winning_bid:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid == self.winning_bid:
    #                 # if there's a tie, bidder with the smallest id wins
    #                 _, their_id = other.bidder.split('_')
    #                 _, my_id = self.bidder.split('_')

    #                 their_id = int(their_id); my_id = int(my_id)

    #                 if their_id < my_id:
    #                     #update and rebroadcast
    #                     pass

    #             elif other.winning_bid < self.winning_bid:
    #                 # update time and rebroadcast
    #                 pass

    #         elif self.winner == other.bidder:
    #             # update and rebroadcast
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass

    #             elif other.t_update < self.t_update:
    #                 # leave and rebroadcast
    #                 pass

    #         elif self.winner not in [self.bidder, other.bidder, other.winner]:
    #             if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
    #                 # leave and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
    #                 # leave and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # update and rebroadcast
    #             pass

    #     elif other.winner is other.NONE:
    #         if self.winner == self.bidder:
    #             # leave and rebroadcast
    #             pass

    #         elif self.winner == other.bidder:
    #             # update and rebroadcast
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # leave and no rebroadcast
    #             pass

    # def __le__(self, other : object) -> bool:
    #     pass

    # def __gt__(self, other : object) -> bool:
    #     """
    #     Compares to other bid and returns true if it has not been outbid
    #     """
    #     other : TaskBid
    #     if self.task_id != other.task_id:
    #         # if update is for a different task, ignore update
    #         raise AttributeError(f'cannot compare bidsintended for different tasks (expected task id: {self.task_id}, given id: {other.task_id})')
        
    #     if other.winner == other.bidder:
    #         if self.winner == self.bidder:
    #             if other.winning_bid > self.winning_bid:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid == self.winning_bid:
    #                 # if there's a tie, bidder with the smallest id wins
    #                 _, their_id = other.bidder.split('_')
    #                 _, my_id = self.bidder.split('_')
    #                 their_id = int(their_id); my_id = int(my_id)

    #                 if their_id < my_id:
    #                     # update and rebroadcast
    #                     pass

    #             if other.winning_bid < self.winning_bid:
    #                 # update time and rebroadcast
    #                 pass

    #         elif self.winner == other.bidder:
    #             if other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #             elif abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass

    #             elif other.t_update < self.t_update:
    #                 # leave and not rebroadcast
    #                 pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
    #                 #leave and rebroadcast
    #                 pass

    #             elif other.winning_bid == self.winning_bid:
    #                 # leave and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # update and rebroadcast
    #             pass

    #     elif other.winner == self.bidder:
    #         if self.winner == self.bidder:
    #             if abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass
                
    #         elif self.winner == other.bidder:
    #             # reset and rebroadcast with current update time
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             # leave and rebroadcast
    #             pass

    #         elif self.winner == self.NONE:
    #             # leave and rebroadcast with current update time
    #             pass

    #     elif other.winner not in [self.bidder, other.bidder]:
    #         if self.winner == self.bidder:
    #             if other.winning_bid > self.winning_bid:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid == self.winning_bid:
    #                 # if there's a tie, bidder with the smallest id wins
    #                 _, their_id = other.bidder.split('_')
    #                 _, my_id = self.bidder.split('_')

    #                 their_id = int(their_id); my_id = int(my_id)

    #                 if their_id < my_id:
    #                     #update and rebroadcast
    #                     pass

    #             elif other.winning_bid < self.winning_bid:
    #                 # update time and rebroadcast
    #                 pass

    #         elif self.winner == other.bidder:
    #             # update and rebroadcast
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif abs(other.t_update - self.t_update) < 1e-6:
    #                 # leave and no rebroadcast
    #                 pass

    #             elif other.t_update < self.t_update:
    #                 # leave and rebroadcast
    #                 pass

    #         elif self.winner not in [self.bidder, other.bidder, other.winner]:
    #             if other.winning_bid > self.winning_bid and other.t_update >= self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #             elif other.winning_bid < self.winning_bid and other.t_update <= self.t_update:
    #                 # leave and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid < self.winning_bid and other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass
                    
    #             elif other.winning_bid > self.winning_bid and other.t_update < self.t_update:
    #                 # leave and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # update and rebroadcast
    #             pass

    #     elif other.winner is other.NONE:
    #         if self.winner == self.bidder:
    #             # leave and rebroadcast
    #             pass

    #         elif self.winner == other.bidder:
    #             # update and rebroadcast
    #             pass

    #         elif self.winner not in [self.bidder, other.bidder]:
    #             if other.t_update > self.t_update:
    #                 # update and rebroadcast
    #                 pass

    #         elif self.winner == self.NONE:
    #             # leave and no rebroadcast
    #             pass

    # def __ge__(self, other : object) -> bool:
    #     pass

    # def __eq__(self, other : object) -> bool:
    #     pass

    # def __ne__(self, other : object) -> bool:
    #     pass

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this bid
        """
        return dict(self.__dict__)

    def copy(self) -> object:
        """
        Returns a deep copy of this bid
        """
        return TaskBid(self.task, self.bidder, self.winning_bid, self.winner, self.t_arrive, self.t_update)

class ACCBBAPlannerModule(PlannerModule):
    """
    # Asynchronous Consensus Constraint-Based Bundle Algorithm
    
    """
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
        self.listener_results = None
        self.bundle_builder_results = None
    
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

            # create poller for all broadcast sockets
            poller = azmq.Poller()
            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            poller.register(manager_socket, zmq.POLLIN)

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                sockets = dict(await poller.poll())

                if manager_socket in sockets:
                    self.log('listening to manager broadcast!')
                    _, _, content = await self.listen_manager_broadcast()

                    # if sim-end message, end agent `live()`
                    if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                        self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                        return

                    if content['msg_type'] == SimulationMessageTypes.SENSES.value:
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
                                await self.outgoing_bundle_builder_inbox.put(out_msg)

                            elif sense['msg_type'] == SimulationMessageTypes.TASK_BID.value:
                                # unpack message 
                                bid_msg : TaskBidMessage = TaskBidMessage(**sense)
                                their_bid = TaskBid(**bid_msg.bid)
                                self.log(f"received a bid from anoger agent for task {their_bid.task_id}!")

                                if their_bid.task_id not in results:
                                    # bid is for a task that I was not aware of; create new empty bid for it and compare
                                    self.log(f"task in question had not been received by this agent. Creating empty bid...")
                                    my_bid = TaskBid(their_bid.task, self.get_parent_name())
                                    results[their_bid.task_id] = my_bid
                                
                                # compare bid 
                                self.log(f"comparing bids for task {their_bid.task_id}...")
                                my_bid : TaskBid = results[their_bid.task_id]
                                self.log(f'original bid: {my_bid}')
                                broadcast_bid : TaskBid = my_bid.update(their_bid.to_dict(), t_curr)
                                self.log(f'updated bid: {my_bid}')
                                results[my_bid.task_id] = my_bid
                                
                                if broadcast_bid is not None:
                                    # if relevant changes were made, send to bundle builder and to out-going inbox 
                                    self.log(f'relevant changes made to bid. Informing bundle-builder')
                                    out_msg = TaskBidMessage(   
                                                            self.get_parent_name(), 
                                                            self.get_parent_name(), 
                                                            broadcast_bid.to_dict()
                                                        )
                                    await self.relevant_changes_inbox.put(out_msg)
                                    await self.outgoing_listen_inbox.put(out_msg) 

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
        t_update = 0.0
        t_next = 0.0
        f_update = 1.0
        
        try:
            while True:
                # wait for next periodict check
                state_msg : AgentStateMessage = await self.states_inbox.get()
                state = SimulationAgentState(**state_msg.state)
                t_curr = state.t
                
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
                    self.log(f'comparing bids:\n\tmy bid: {my_bid}\n\ttheir bid: {their_bid}')
                    broadcast_bid : TaskBid = my_bid.update(their_bid.to_dict(), t_curr)
                    self.log(f'bid updated:\n{my_bid}')
                    results[my_bid.task_id] = my_bid
                        
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
                    if broadcast_bid is not None and broadcast_bid in bundle:
                        bid_index = bundle.index(broadcast_bid)

                        for _ in range(bid_index, len(bundle)):
                            # remove task from bundle
                            task = bundle.pop(bid_index)
                            path.remove(task)

                # update bundle from new information
                available_tasks : list = self.get_available_tasks(state, bundle, results)
                while len(bundle) < self.l_bundle and len(available_tasks) > 0:                    
                    current_bids = {task.id : results[task.id] for task in bundle}
                    max_path = None; max_task = None; max_path_bids = None
                    max_path_utility = self.sum_path_utility(path, current_bids)
                    # find next best task to put in bundle (greedy)
                    for task in available_tasks:
                        # calculate bid for a given available task
                        task : MeasurementTask
                        projected_path, projected_bids, projected_path_utility = self.calc_path_bid(state, path, task)
                        
                        # compare to maximum task
                        if max_path is None or projected_path_utility > max_path_utility:
                            max_path = projected_path
                            max_task = task
                            max_path_bids = projected_bids
                            max_path_utility = projected_path_utility

                    if max_path is not None: # max bid found!
                        # place task with the best bid in the bundle and the path
                        bundle.append(max_task)
                        path = max_path
                        
                        # update bids
                        for task in bundle:
                            task : MeasurementTask
                            bid : TaskBid = max_path_bids[task.id]
                            current_bid : TaskBid = results[task.id]
                            current_bid.update(bid.to_dict(), t_curr)
                            results[task.id] = current_bid

                            # add to changes broadcast
                            out_msg = TaskBidMessage(   
                                                    self.get_parent_name(), 
                                                    self.get_parent_name(), 
                                                    current_bid.to_dict()
                                                )
                            changes.append(out_msg)

                        # remove bid task from list of available tasks
                        available_tasks.remove(max_task)

                    else:
                        # no max bid was found; no more tasks can be added to the bundle
                        break

                # send changes to rebroadcaster
                for change in changes:
                    await self.outgoing_bundle_builder_inbox.put(change)

                # DEBUG PURPOSES ONLY: instructs agent to idle and only messages/listens to agents
                action = WaitForMessages(t_curr, t_curr + 1/f_update)
                await self.outgoing_bundle_builder_inbox.put(action)

        except asyncio.CancelledError:
            return

        finally:
            self.bundle_builder_results = results

    def get_available_tasks(self, state : SimulationAgentState, bundle : list, results : dict) -> list:
        """
        Checks if there are any tasks available to be performed

        ### Returns:
            - list containing all available and bidable tasks to be performed by the parent agent
        """
        available = []
        for task_id in results:
            bid : TaskBid = results[task_id]
            task = MeasurementTask(**bid.task)

            if self.can_bid(state, task) and task not in bundle:
                available.append(task)

        return available

    def can_bid(self, state : SimulationAgentState, task : MeasurementTask) -> bool:
        """
        Checks if an agent can perform a measurement task
        """
        # check capabilities - TODO: Replace with knowledge graph
        for instrument in task.instruments:
            if instrument not in state.instruments:
                return False

        # check time constraints
        ## Constraint 1: task must be able to be performed durig or after the current time
        if task.t_end < state.t:
            return False
        
        return True

    def calc_path_bid(self, state : SimulationAgentState, original_path : list, task : MeasurementTask) -> tuple:
        """
        Calculates the best possible bid for a given task and creates the best path to accomodate said task

        ### Arguments:
        - state (:obj:`SimulationAgentState`): latest known state of the agent
        - original_path (`list`): sequence of tasks to be performed under the current plan
        - task (:obj:`MeasurementTask`): task to be scheduled

        ### Returns:
        - winning_path (`list`): list indicating the best path if `task` was to be performed. 
                            Is of type `NoneType` if no suitable path can be found for `task`.
        - winning_bids (`dict`): dictionary mapping task IDs to their proposed bids if the winning 
                            path is to be scheduled. Is of type `NoneType` if no suitable path can 
                            be found.
        - winning_path_utility (`float`): projected utility of executing the winning path
        """
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
                t_arrive = self.calc_arrival_time(state, path, bids, task_i)

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
    
    def sum_path_utility(self, path : list, bids : dict) -> float:
        """
        Sums the utilities of a proposed path
        """
        utility = 0.0
        for task in path:
            task : MeasurementTask
            bid : TaskBid = bids[task.id]
            utility += bid.own_bid

        return utility
    
    def calc_utility(self, task : MeasurementTask, t_arrive : float):
        """
        Calculates the expected utility of performing a measurement task
        """
        # check time constraints
        if t_arrive < task.t_start or task.t_end < t_arrive:
            return 0.0
        
        # calculate urgency factor from task
        urgency = np.log(1e-3) / (task.t_start - task.t_end)

        return task.s_max * np.exp( -urgency * (t_arrive - task.t_start) )

    def calc_arrival_time(self, state : SimulationAgentState, path : list, bids : dict, task : MeasurementTask) -> float:
        """
        Computes the time when a task in the path would be performed
        """
        # calculate the previous task's position and 
        i = path.index(task)
        if i == 0:
            t_prev = state.t
            pos_prev = state.pos
        else:
            task_prev : MeasurementTask = path[i-1]
            bid_prev : TaskBid = bids[task_prev]
            t_prev : float = bid_prev.t_arrive + task_prev.duration
            pos_prev : list = task_prev.pos

        # compute travel time to the task
        pos_next = task.pos
        dpos = np.sqrt( (pos_next[0]-pos_prev[0])**2 + (pos_next[1]-pos_prev[1])**2 )
        t_travel = dpos / state.v_max
        t_arrival = t_travel + t_prev

        return t_arrival if t_arrival >= task.t_start else task.t_start

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
                while True:
                    bundle_msgs.append(await self.outgoing_bundle_builder_inbox.get())
                    
                    if self.outgoing_bundle_builder_inbox.empty():
                        await asyncio.sleep(1e-2)
                        if self.outgoing_bundle_builder_inbox.empty():
                            break

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
                            if bundle_bid.t_update > listener_bid.t_update:
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
                if len(actions) > 0:
                    x=1
                self.log(f'bids compared! generating plan with {len(bid_messages)} bid messages and {len(actions)} actions')
                plan_msg = PlanMessage(self.get_element_name(), self.get_parent_name(), plan)
                await self._send_manager_msg(plan_msg, zmq.PUB)
                self.log(f'actions sent!')

        except asyncio.CancelledError:
            pass

    async def teardown(self) -> None:
        # print listener bidding results
        with open(f"{self.results_path}/{self.get_parent_name()}/listener_bids.csv", "w") as file:
            title = "task_id,bidder,own_bid,winner,winning_bid,t_arrive,t_update"
            file.write(title)

            for task_id in self.listener_results:
                bid : TaskBid = self.listener_results[task_id]
                file.write('\n' + str(bid))

        # print bundle-builder bidding results
        with open(f"{self.results_path}/{self.get_parent_name()}/bundle_builder_bids.csv", "w") as file:
            title = "task_id,bidder,own_bid,winner,winning_bid,t_arrive,t_update"
            file.write(title)

            for task_id in self.bundle_builder_results:
                bid : TaskBid = self.bundle_builder_results[task_id]
                file.write('\n' + str(bid))