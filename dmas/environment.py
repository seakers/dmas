import asyncio
from beartype import beartype
import zmq
from dmas.node import AbstractSimulationNode
from dmas.utils import *

class AbstractEnvironmentNode(AbstractSimulationNode):
    """
    ## Abstract Environment Node 

    Base class for all environment servers nodes.

    ### Attributes:
        - _name (`str`): The name of this simulation element
        - _network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
        - _my_addresses (`list`): List of addresses used by this simulation element
        - _logger (`Logger`): debug logger

        - _pub_socket (:obj:`Socket`): The node's broadcast port socket
        - _pub_socket_lock (:obj:`Lock`): async lock for _pub_socket (:obj:`Socket`)
        - _sub_socket (:obj:`Socket`): The node's broadcast reception port socket
        - _sub_socket_lock (:obj:`Lock`): async lock for _sub_socket (:obj:`Socket`)
        - _req_socket (:obj:`Socket`): The node's request port socket
        - _req_socket_lock (:obj:`Lock`): async lock for _req_socket (:obj:`socket`)
        - _rep_socket (:obj:`Socket`): The node's response port socket
        - _rep_socket_lock (:obj:`Lock`): async lock for _rep_socket (:obj:`socket`)
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`Socket`)

    ### Communications diagram:
    +----------+---------+       
    |          | PUB     |------>
    |          +---------+       
    |          | SUB     |<------
    | ABSTRACT +---------+       
    |   ENV    | REQ     |<<---->
    |   NODE   +---------+       
    |          | REP     |<---->>
    |          +---------+       
    |          | PUSH    |------>
    +----------+---------+       
    """
    @beartype
    def __init__(self, name: str, network_config: EnvironmentNetworkConfig) -> None:
        super().__init__(name, network_config)

    async def _config_network(self) -> list:
        """
        Initializes and connects essential network port sockets for a simulation manager. 
        
        #### Sockets Initialized:
            - _pub_socket (:obj:`Socket`): The node's response port socket
            - _sub_socket (:obj:`Socket`): The node's reception port socket
            - _req_socket (:obj:`Socket`): The node's request port socket
            - _rep_socket (:obj:`Socket`): The node's response port socket
            - _monitor_push_socket (:obj:`Socket`): The node's monitor port socket

        #### Returns:
            - port_list (`list`): contains all sockets used by this simulation element
        """
        port_list : list = await super()._config_network()

        # response port
        self._rep_socket = self._context.socket(zmq.REP)
        self._network_config : EnvironmentNetworkConfig
        self._rep_socket.bind(self._network_config.get_response_address())
        self._rep_socket.setsockopt(zmq.LINGER, 0)
        self._rep_socket_lock = asyncio.Lock()

        port_list.append(self._rep_socket)

        return port_list

if __name__ == "__main__":
    
    @beartype
    @abstractmethod
    def foo(x : int):
        pass
    
    foo(1)
    foo('x')
    