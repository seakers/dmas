from abc import ABC, abstractmethod
import asyncio
import datetime
import json
import logging
from typing import Union
import uuid
import zmq
from zmq import asyncio as azmq

from dmas.messages import ManagerMessageTypes, SimulationElementRoles, TocMessage
from dmas.network import NetworkConfig
from dmas.nodes import Node

class FailureStateException(Exception):
    pass

class AgentState(ABC):
    """
    Describes the state of an agent
    """
    @abstractmethod
    def update_state(self, **kwargs):
        """
        Updates the state of this agent
        """
        pass

    @abstractmethod
    def is_critial(self, **kwargs) -> bool:
        """
        Returns true if the state is a critical state
        """
        pass

    @abstractmethod
    def is_failure(self, **kwargs) -> bool:
        """
        Returns true if the state is a failure state
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
        - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
        - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
        - id (`str`) : identifying number for this task in uuid format
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
                    **a2016761
                    
                ) -> None:
        """
        Creates an instance of an agent action

        ### Arguments:
            - t_start (`float`): start time of the availability of this task in [s] from the beginning of the simulation
            - t_end (`float`): end time of the availability of this task in [s] from the beginning of the simulation
            - id (`str`) : identifying number for this task in uuid format
        """
        super().__init__()

        if not isinstance(t_start, float) and not isinstance(t_start, int):
            raise AttributeError(f'`t_start` must be of type `float` or type `int`. is of type {type(t_start)}.')
        elif t_start < 0:
            raise ValueError(f'`t_start` must be a value higher than 0. is of value {t_start}.')
        if not isinstance(t_end, float) and not isinstance(t_end, int):
            raise AttributeError(f'`t_end` must be of type `float` or type `int`. is of type {type(t_end)}.')
        elif t_end < 0:
            raise ValueError(f'`t_end` must be a value higher than 0. is of value {t_end}.')
        
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
                    initial_state: AgentState,
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
                            level, 
                            logger)
        
        if zmq.REQ not in agent_network_config.get_external_addresses() and zmq.DEALER not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a REQ or DEALER port and an address within its external address map.')
        if zmq.PUB not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a PUB port and an address within its external address map.')
        if zmq.SUB not in agent_network_config.get_external_addresses():
            raise AttributeError(f'`node_network_config` must contain a SUB port and an address within its external address map.')

        self.state : AgentState = initial_state

    async def _activate(self) -> None:
        await super()._activate()

        self.environment_inbox = asyncio.Queue()

    async def live(self):
        try:
            t_1 = asyncio.create_task(self.routine(), name='routine()')
            t_2 = asyncio.create_task(self.listen_to_broadcasts(), name='listen()')

            _, pending = await asyncio.wait([t_1, t_2], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task : asyncio.Task
                task.cancel()
                await task
        
        except asyncio.CancelledError:
            return

    async def routine(self):
        """
        Agent performs sense, thinkg, and do loop while state is . 
        """
        try:
            statuses = dict()
            while not self.state.is_failure():
                # sense environment
                senses = await self.sense(statuses)

                # think of next action(s) to take
                actions = await self.think(senses)

                # perform action(s)
                statuses = await self.do(actions)
        
        except asyncio.CancelledError:
            return        
        
        except FailureStateException:
            return

    async def listen_to_broadcasts(self):
        """
        Listens for any incoming broadcasts and classifies them in their respective inbox
        """
        try:
            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            external_socket, _ = self._external_socket_map.get(zmq.SUB)
            internal_socket, _ = self._external_socket_map.get(zmq.SUB)

            poller = azmq.Poller()
            poller.register(manager_socket, zmq.POLLIN)
            poller.register(external_socket, zmq.POLLIN)
            poller.register(internal_socket, zmq.POLLIN)

            while True:
                sockets = dict(await poller.poll())

                if manager_socket in sockets:
                    dst, src, content = await self.listen_manager_broadcast()

                    # if sim-end message, end process
                    if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                        return

                    # else, let agent handle it
                    else:
                        self.manager_inbox.put( (dst, src, content) )
                
                if external_socket in sockets:
                    dst, src, content = await self.listen_peer_broadcast()

                    if src == SimulationElementRoles.ENVIRONMENT.value:
                        self.environment_inbox.put( (dst, src, content) )
                    else:
                        self.external_inbox.put( (dst, src, content) )

                if internal_socket in sockets: 
                    dst, src, content = await self.listen_internal_broadcast()
                    self.internal_inbox.put( (dst, src, content) )

        except asyncio.CancelledError:
            return  

    @abstractmethod
    async def sense(self, statuses : dict) -> list:
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
    async def do(self, actions : list) -> dict:
        """
        Performs agent actions

        ### Arguments:
            - actions (`list`): list of actions to be performed by the agent

        ### Returns:
            - statuses (`dict`): map of the latest actions performed by the agent and their completion status
        """
        pass
