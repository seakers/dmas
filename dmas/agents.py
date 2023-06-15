from abc import ABC, abstractmethod
import asyncio
import datetime
import json
import logging
import time
from typing import Union
import uuid
import zmq
from zmq import asyncio as azmq

from dmas.messages import ManagerMessageTypes, SimulationElementRoles, TocMessage
from dmas.network import NetworkConfig
from dmas.nodes import Node

class FailureStateException(Exception):
    pass

class AbstractAgentState(ABC):
    """
    Describes the state of an agent
    """
    @abstractmethod
    def update_state(self, **kwargs) -> None:
        """
        Propagates the current state
        """
        pass

    @abstractmethod
    def perform_action(self, **kwargs) -> None:
        """
        Performs an action that may alter the current state
        """
        pass

    @abstractmethod
    def is_failure(self, **kwargs) -> None:
        """
        Checks if the current state is a failure state
        """
        pass

    @abstractmethod
    def __str__(self) -> str:
        """
        Creates a string representing the contents of this agent state
        """
        pass

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this agent state object
        """
        return dict(self.__dict__)

    def __eq__(self, other : object) -> bool:
        """
        Compares two instances of an agent state message. Returns True if they represent the same message.
        """
        return self.to_dict() == dict(other.__dict__)

class AgentAction(ABC):
    """
    ## Agent Action
    
    Describes an action to be performed by an agent

    ### Attributes:
        - action_type (`str`): type of action to be performed
        - t_start (`float`): start time of this action in [s] from the beginning of the simulation
        - t_end (`float`): end time of this this action in [s] from the beginning of the simulation
        - status (`str`): completion status of the action
        - id (`str`) : identifying number for this action in uuid format
    """
    PENDING = 'PENDING'
    COMPLETED = 'COMPLETED'
    ABORTED = 'ABORTED'

    def __init__(   self, 
                    action_type : str,
                    t_start : Union[float, int],
                    t_end : Union[float, int], 
                    status : str = 'PENDING',
                    id : str = None,
                    **_

                ) -> None:
        """
        Creates an instance of an agent action

        ### Arguments:
            - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__()

        # type and value checks
        if not isinstance(t_start, float) and not isinstance(t_start, int):
            raise AttributeError(f'`t_start` must be of type `float` or type `int`. is of type {type(t_start)}.')
        elif t_start < 0:
            raise ValueError(f'`t_start` must be a value higher than 0. is of value {t_start}.')
        if not isinstance(t_end, float) and not isinstance(t_end, int):
            raise AttributeError(f'`t_end` must be of type `float` or type `int`. is of type {type(t_end)}.')
        elif t_end < 0:
            raise ValueError(f'`t_end` must be a value higher than 0. is of value {t_end}.')
        if t_start > t_end:
            raise ValueError(f'`t_start must be lower or equal than `t_end` (t_start: {t_start}, t_end: {t_end}.')

        # assign values 
        self.action_type = action_type
        self.t_start = t_start
        self.t_end = t_end
        self.status = status
        self.id = str(uuid.UUID(id)) if id is not None else str(uuid.uuid1())

    def __eq__(self, other) -> bool:
        """
        Compares two instances of a task. Returns True if they represent the same task.
        """
        return self.to_dict() == dict(other.__dict__)

    def to_dict(self) -> dict:
        """
        Crates a dictionary containing all information contained in this task object
        """
        return dict(self.__dict__)
    
    def to_json(self) -> str:
        """
        Creates a json file from this task 
        """
        return json.dumps(self.to_dict())

    def __str__(self) -> str:
        """
        Creates a string representing the contents of this task
        """
        return str(self.to_dict())
    
class Agent(Node):
    """
    ## Agent Node

    Agent living within a DMAS simulation.

    ### Attributes:
        - state (:obj:`AgentState`): object describing the current state of the agent
    """
    def __init__(self, 
                    agent_name: str, 
                    agent_network_config: NetworkConfig, 
                    manager_network_config: NetworkConfig, 
                    initial_state: AbstractAgentState,
                    modules: list = [], 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:
        """
        Creates an instance of an Agent object

        ### Arguments:
            - agent_name (`str`): name of the agent
            - agent_network_config (:obj:`NetworkConfig`): network configuration for the agent's network ports
            - manager_network_config (:obj:`NetworkConfig`): simulation manager's network configuration
            - initial_state (:obj:`AgentState`): initial agent state
            - modules (`list`): list of `InternalModule`s contained within the agent
            - level (`int`): logging level
            - logger (`logging.Logger`): logger
            - state (:obj:`AgentState`): object describing the current state of the agent
        """
        super().__init__(   agent_name, 
                            agent_network_config, 
                            manager_network_config, 
                            modules, 
                            level=level, 
                            logger=logger)
        
        if zmq.REQ not in agent_network_config.get_external_addresses() and zmq.DEALER not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a REQ or DEALER port and an address within its external address map.')
        if zmq.PUB not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a PUB port and an address within its external address map.')
        if zmq.SUB not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a SUB port and an address within its external address map.')

        self.state : AbstractAgentState = initial_state
        self.stats = {
                        'sense' : [],
                        'think' : [],
                        'do' : []
                    }

    async def _activate(self) -> None:
        await super()._activate()

        self.environment_inbox = asyncio.Queue()

    async def live(self):
        try:
            # subscribe to environment broadcasts
            self.subscribe_to_broadcasts(SimulationElementRoles.ENVIRONMENT.value)

            # run `routine()` and `listen()` until the one terminates
            t_1 = asyncio.create_task(self.reactive_routine(), name='reactive_routine()')
            t_2 = asyncio.create_task(self.listen_to_broadcasts(), name='listen_to_broadcasts()')

            done, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                self.log(f'`{task.get_name()}` task finalized! Terminating all other tasks...')

            # cancel pending task
            for task in pending:
                task : asyncio.Task
                self.log(f'Terminating task `{task.get_name()}`...')
                while not task.done():
                    task.cancel()
                    timeout_task = asyncio.sleep(1e-2)
                    await asyncio.wait([task, timeout_task], return_when=asyncio.FIRST_COMPLETED)

                self.log(f'`{task.get_name()}` task terminated!')
        
        except asyncio.CancelledError:
            return

    async def reactive_routine(self):
        """
        Agent performs sense-think-do loop 
        """
        try:
            statuses = []
            while not self.state.is_failure():
                # sense environment
                self.log('sensing...')
                t_0 = time.perf_counter()
                senses = await self.sense(statuses)
                dt = time.perf_counter() - t_0
                self.stats['sense'].append(dt)

                # think of next action(s) to take
                self.log('thinking...')
                t_0 = time.perf_counter()
                actions = await self.think(senses)
                dt = time.perf_counter() - t_0
                self.stats['think'].append(dt)

                # perform action(s)
                t_0 = time.perf_counter()
                self.log('performing action(s)...')
                statuses = await self.do(actions)
                dt = time.perf_counter() - t_0
                self.stats['do'].append(dt)
        
        except asyncio.CancelledError:
            return        
        
        except FailureStateException:
            return
                
    async def listen_to_broadcasts(self):
        """
        Listens for any incoming broadcasts and classifies them in their respective inbox
        """
        try:
            # create poller for all broadcast sockets
            poller = azmq.Poller()

            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            external_socket, _ = self._external_socket_map.get(zmq.SUB)
            internal_socket, _ = self._internal_socket_map.get(zmq.SUB)

            poller.register(manager_socket, zmq.POLLIN)
            poller.register(external_socket, zmq.POLLIN)
            poller.register(internal_socket, zmq.POLLIN)

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                sockets = dict(await poller.poll())

                if manager_socket in sockets:
                    self.log('listening to manager broadcast!')
                    dst, src, content = await self.listen_manager_broadcast()

                    # if sim-end message, end agent `live()`
                    if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                        self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                        return

                    # else, let agent handle it
                    else:
                        self.log(f"received manager broadcast or type {content['msg_type']}! sending to inbox...")
                        await self.manager_inbox.put( (dst, src, content) )
                
                if external_socket in sockets:
                    dst, src, content = await self.listen_peer_broadcast()

                    if src == SimulationElementRoles.ENVIRONMENT.value:
                        self.log('received environment broadcast! sending to inbox...')
                        await self.environment_inbox.put( (dst, src, content) )
                        self.log(f'environment inbox contains {self.environment_inbox.qsize()} messages.')
                    else:
                        self.log('received peer broadcast! sending to inbox...')
                        await self.external_inbox.put( (dst, src, content) )
                        self.log(f'external inbox contains {self.external_inbox.qsize()} messages.')

                if internal_socket in sockets: 
                    dst, src, content = await self.listen_internal_broadcast()
                    self.log('received internal broadcast! sending to inbox...')
                    await self.internal_inbox.put( (dst, src, content) )

        except asyncio.CancelledError:
            return  

    @abstractmethod
    async def sense(self, statuses : list) -> list:
        """
        Senses the environment and checks for any incoming messages from other agents.
        It may also check the status of the actions that were just performed.

        ### Arguments:
            - statuses (`dict`): map of the latest actions performed by the agent and their completion status

        ### Returns:
            - senses (`list`): list of messages containing information sensed by the agent
        """
        pass

    @abstractmethod
    async def think(self, senses : list) -> list:
        """
        Processes sensed information and generates an informed list of actions to perform next

        ### Arguments:
            - senses (`dict`): list of messages containing information sensed by the agent

        ### Returns:
            - actions (`list`): list of actions to be performed by the agent
        """
        pass

    @abstractmethod
    async def do(self, actions : list) -> list:
        """
        Performs agent actions

        ### Arguments:
            - actions (`list`): list of actions to be performed by the agent

        ### Returns:
            - statuses (`dict`): map of the latest actions performed by the agent and their completion status
        """
        pass
