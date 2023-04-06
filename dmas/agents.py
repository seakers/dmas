from abc import ABC, abstractmethod
import logging
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
        pass

class Agent(Node):
    def __init__(self, 
                    agent_name: str, 
                    agent_network_config: NetworkConfig, 
                    manager_network_config: NetworkConfig, 
                    initial_state: AgentState,
                    modules: list = [], 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:

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