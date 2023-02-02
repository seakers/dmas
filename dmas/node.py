import asyncio
import logging
from beartype import beartype
import zmq

from dmas.element import AbstractSimulationElement
from dmas.messages import *
from dmas.utils import *

class AbstractSimulationNode(AbstractSimulationElement):
    """
    ## Abstract Simulation Node 

    Base class for all simulation nodes. This including all agents and the environment in which they live in.

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
        - _req_socket_lock (:obj:`Lock`): async lock for _peer_out_socket (:obj:`socket`)
        - _monitor_push_socket (:obj:`Socket`): The element's monitor port socket
        - _monitor_push_socket_lock (:obj:`Lock`): async lock for _monitor_push_socket (:obj:`Socket`)

    ### Communications diagram:
    +----------+---------+       
    |          | PUB     |------>
    |          +---------+       
    | ABSTRACT | SUB     |<------
    |   SIM    +---------+       
    |   NODE   | REQ     |<<---->
    |          +---------+       
    |          | PUSH    |------>
    +----------+---------+       
    """
    @beartype
    def __init__(self, 
                name : str, 
                network_config : NodeNetworkConfig, 
                level : int = logging.INFO
                ) -> None:
        """
        Initiates a new instance of an abstract node object

        ### Args:
            - name (`str`): The object's name
            - network_config (:obj:`NodeNetworkConfig`): description of the addresses pointing to this simulation node
            - level (`int`): logging level for this simulation element
        """
        super().__init__(name, network_config, level)
    
    async def _config_network(self) -> list:
        """
        Initializes and connects essential network port sockets for a simulation manager. 
        
        #### Sockets Initialized:
            - _pub_socket (:obj:`Socket`): The node's response port socket
            - _sub_socket (:obj:`Socket`): The node's reception port socket
            - _req_socket (:obj:`Socket`): The node's request port socket
            - _monitor_push_socket (:obj:`Socket`): The node's monitor port socket

        #### Returns:
            - port_list (`list`): contains all sockets used by this simulation element
        """
        port_list : list = await super()._config_network()

        # broadcast reception port 
        self._sub_socket = self._context.socket(zmq.SUB)
        self._network_config : NodeNetworkConfig
        self._name : str
        all_str : str = str(SimulationElementTypes.ALL.name)
        self._sub_socket.connect(self._network_config.get_subscribe_address)
        self._sub_socket.setsockopt(zmq.SUBSCRIBE, self.name.encode('ascii'))
        self._sub_socket.setsockopt(zmq.SUBSCRIBE, all_str.encode('ascii'))
        self._sub_socket.setsockopt(zmq.LINGER, 0)
        self._sub_socket_lock = asyncio.Lock()

        port_list.append(self._sub_socket)

        # direct message response port
        self._req_socket = self._context.socket(zmq.REQ)
        self._req_socket.setsockopt(zmq.LINGER, 0)
        self._req_socket_lock = asyncio.Lock()

        port_list.append(self._req_socket)

        return port_list

    async def _send_manager_message(self, msg : SimulationMessage):
        try:
            self._log(f'acquiring port lock for a message of type {type(msg)}...')
            await self._req_socket_lock.acquire()
            self._log(f'port lock acquired!')
            
            self._log(f'connecting to simulation manager...')
            self._network_config : NodeNetworkConfig
            self._req_socket.connect(self._network_config.get_manager_address())
            self._log(f'successfully connected to simulation manager!')

            self._log(f'sending message of type {type(msg)}...')
            dst : str = msg.get_dst()
            content : str = str(msg.to_json())

            if dst != SimulationElementTypes.MANAGER.value:
                raise asyncio.CancelledError('attempted to send a non-manager message to the simulation manager.')
            
            await self._req_socket.send_multipart([dst, content])
            self._log(f'message transmitted sucessfully!')

        except asyncio.CancelledError as e:
            self._log(f'message transmission interrupted. {e}')
            
        except:
            self._log(f'message transmission failed.')
            raise

        finally:
            self._req_socket_lock.release()
            self._log(f'port lock released.')
    