from abc import ABC, abstractmethod
import asyncio
import datetime
import logging
from typing import Union
import zmq

from dmas.network import NetworkConfig
from dmas.nodes import Node

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
        - t_start (`float` or `int`): start time of the action in [s] 
        - t_end (`float` or `int`): end time of the action in [s] 
    """
    PENDING = 'PENDING'
    COMPLETED = 'COMPLETED'
    ABORTED = 'ABORTED'

    def __init__(self, t_start : Union[float, int], t_end : Union[float, int]) -> None:
        """
        Creates an instance of an agent action

        ### Arguments:
            - t_start (`float` or `int`): start time of the action in [s] 
            - t_end (`float` or `int`): end time of the action in [s] 
        """
        super().__init__()
        self.t_start = t_start
        self.t_end = t_end

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

    async def live(self):
        try:
            statuses = dict()
            while True:
                # sense environment
                senses = await self.sense(statuses)

                # think of next action(s) to take
                actions = await self.think(senses)

                # perform action(s)
                statuses = await self.do(actions)
        
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
