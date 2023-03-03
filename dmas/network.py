from abc import ABC
import logging
import socket
import zmq
import zmq.asyncio as azmq
import asyncio
from dmas.messages import *

"""
------------------
NETWORK CONFIG
------------------
"""
class NetworkConfig(ABC):
    """
    ## Network Configuration Object

    Describes the internal and external network ports assigned to a network element.

    #### Attributes:
        - network_name (`str`): name of the network this configuration belongs to
        - internal_address_map (`dict`): dictionary mapping types of network ports to their internal network addresses to be bound or connected to
        - external_address_map (`dict`): dictionary mapping types of network ports to their internal network addresses to be bound or connected to

    """
    def __init__(self, network_name : str, internal_address_map : dict = dict(), external_address_map : dict = dict()) -> None:
        """
        Creates an instance of a Network Config Object

        ### Arguments:
            - network_name (`str`): name of the network this configuration belongs to
            - internal_address_map (`dict`): dictionary mapping types of network ports to their internal network addresses to be bound or connected to
            - external_address_map (`dict`): dictionary mapping types of network ports to their internal network addresses to be bound or connected to
        """
        super().__init__()  
        # save network name 
        if not isinstance(network_name, str):
            raise TypeError(f'Expected `network_name` to be of type `str`. Is of type {type(network_name)}')
        self.network_name = network_name

        # check map format
        for map in [internal_address_map, external_address_map]:

            sockets_to_delete = []
            sockets_to_add = []

            for socket_type in map:
                addresses = map[socket_type]

                if not isinstance(socket_type, type(zmq.PUB)):
                    # if socket type was serialized into an `int` when turned into a dictionaty, fin equivalent zmq socket type
                    new_socket_type = None
                    
                    for socketType in zmq.SocketType:
                        if socketType.value == int(socket_type):
                            new_socket_type = socketType
                            break

                    if new_socket_type is not None:
                        # if an equivalent socket type is found, remove dictionary entry and replace with equivalent socket
                        sockets_to_add.append((new_socket_type, map[socket_type]))
                        sockets_to_delete.append(socket_type)
                        
                    else:
                        # if not equivalent socket type is found, raise an exception
                        if map == internal_address_map:
                            raise TypeError(f'Socket of type {socket_type} in Internal Address Map must be of type {type(zmq.PUB)}. Is of type {type(socket_type)}')
                        else:
                            raise TypeError(f'Socket of type {socket_type} in External Address Map must be of type {type(zmq.PUB)}. Is of type {type(socket_type)}')

                
                if len(addresses) > 0 and not isinstance(addresses, list):
                    if map == internal_address_map:
                        raise TypeError(f'Internal Address Map must be comprised of elements of type {list}. Is of type {type(addresses)}')
                    else:
                        raise TypeError(f'External Address Map must be comprised of elements of type {list}. Is of type {type(addresses)}')

                for address in addresses:   
                    if not isinstance(address, str):
                        if map == internal_address_map:
                            raise TypeError(f'{address} in Internal Address Map must be of type {type(str)}. Is of type {type(address)}')
                        else:
                            raise TypeError(f'{address} in External Address Map must be of type {type(str)}. Is of type {type(address)}')

            for socket_type in sockets_to_delete:
                map.pop(socket_type)
            
            for socket_type, addresses in sockets_to_add:
                map[socket_type] = addresses

        # save addresses
        self.internal_address_map = internal_address_map.copy()
        self.external_address_map = external_address_map.copy()

    def __eq__(self, other) -> bool:
        """
        Compares two instances of a network configuration. Returns True if they represent the same configuration.
        """
        return self.to_dict() == other.to_dict()

    def get_internal_addresses(self) -> dict:
        """
        Returns the configuration's internal socket addresses 
        """
        return self.internal_address_map

    def get_external_addresses(self) -> dict:
        """
        Returns the configuration's external socket addresses 
        """
        return self.external_address_map

    def to_dict(self) -> dict:
        """
        Creates a dictionary containig all attributes of this object
        """
        return self.__dict__
    
    def to_json(self) -> str:
        """
        Creates a json serializable string containig all attributes of this object
        """
        return json.dumps(self.to_dict())
    
    def is_port_in_use(self, port: int) -> bool:
        """
        Checks if a port is currently being used by a socket
        """
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def get_next_available_port(self):
        """
        Searches to find the next available port in the `localhost` network
        """
        port = 5555
        while self.is_port_in_use(port):
            port += 1
        return port
    
    def get_next_available_local_address(self):
        
        """
        Searches to find the next available network address in the `localhost` network
        """
        port = self.get_next_available_port()
        return f'tcp://localhost:{port}'

"""
------------------
NETWORK ELEMENT
------------------
"""
class NetworkElement(ABC):
    """
    ## Abstract Network Element 

    Abstract class for all DMAS network elements.

    ### Attributes:
        - _network_name (`str`): The name of the network that the element belongs to
        - _element_name (`str`): The element's name
        - _name (`str`): The name of this simulation element with it's network name as a prefix

        - _network_config (:obj:`NetworkConfig`): description of the addresses pointing to this network element
        - _network_context (:obj:`zmq.Context()`): network context used for TCP ports to be used by this network element
        
        - _internal_socket_map (`dict`): Map of ports and port locks to be used by this network element to communicate with internal processes
        - _internal_address_ledger (`dict`): ledger mapping the addresses pointing to this network element's internal communication ports    
        - _external_socket_map (`dict`): Map of ports and port locks to be used by this network element to communicate with other network elements
        - _external_address_ledger (`dict`): ledger mapping the addresses pointing to other network elements' connecting ports    

    +--------------------+                                                                                          
    |  NETWORK ELEMENTS  |                                                                                          
    +--------------------+                                                                                          
              ^                                                                                                     
              |                                                                                                     
              v                                                                                                     
    +--------------------+                                                                                          
    |   External Ports   |                                                                                          
    |--------------------|                                                                                          
    |ABSTRACT NET ELEMENT|                                                                                          
    |--------------------|                                                                                          
    |   Internal Ports   |                                                                                          
    +--------------------+                                                                                          
              ^                                                                                                     
              |                                                                                                     
              v                                                                                                     
    +--------------------+                                                                                          
    | INTERNAL PROCESSES |                                                                                               
    +--------------------+   
    """
    def __init__(self, element_name : str, network_config : NetworkConfig, level : int = logging.INFO, logger : logging.Logger = None) -> None:
        """
        Initiates a new network element

        ### Args:
            - network_name (`str`): The name of the network that the element belongs to
            - element_name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this nmetwork element
        """
        super().__init__()
        
        self._network_name = network_config.network_name
        self._element_name = element_name
        self.name = network_config.network_name + '/' + element_name
        self._logger : logging.Logger = self.__set_up_logger(level) if logger is None else logger

        self._network_config = network_config
        self._internal_socket_map = None
        self._internal_address_ledger = None
        self._external_socket_map = None
        self._external_address_ledger = None

        self.__network_activated = False
        self.__network_synced = False

    def __del__(self):
        """
        Closes all open netowrk connections in case any are open when deleting an instance of this class
        """
        self._deactivate_network() if self.__network_activated else None

    def get_network_name(self) -> str:
        """
        Returns the name of the network that this element belongs to
        """
        return self._network_config.network_name
    
    def get_element_name(self) -> str:
        """
        Returns the name this network element
        """
        return self._element_name
    
    def get_socket_maps(self) -> tuple:
        return self._external_socket_map, self._internal_socket_map
    
    def __set_up_logger(self, level=logging.DEBUG) -> logging.Logger:
        """
        Sets up a logger for this simulation element

        TODO add save to file capabilities
        """
        logger = logging.getLogger()
        logger.propagate = False
        logger.setLevel(level)

        c_handler = logging.StreamHandler()
        c_handler.setLevel(level)
        logger.addHandler(c_handler)

        return logger 
    
    def _log(self, msg : str, level=logging.DEBUG) -> None:
        """
        Logs a message to the desired level.
        """
        if level is logging.DEBUG:
            self._logger.debug(f'{self.name}: {msg}')
        elif level is logging.INFO:
            self._logger.info(f'{self.name}: {msg}')
        elif level is logging.WARNING:
            self._logger.warning(f'{self.name}: {msg}')
        elif level is logging.ERROR:
            self._logger.error(f'{self.name}: {msg}')
        elif level is logging.CRITICAL:
            self._logger.critical(f'{self.name}: {msg}')

    @abstractmethod
    def run(self) -> int:
        """
        Main function. Executes this network element.

        Returns a 1 for a successful execution. Returns a 0 otherwise.
        """
        pass

    def get_network_config(self) -> NetworkConfig:
        """
        Returns network configuration for this network element
        """
        return self._network_config

    """
    NETWORK PORT CONFIG
    """
    def config_network(self) -> tuple:
        """
        Initializes and connects essential network port sockets for this simulation element. 
        
        #### Returns:
            - `tuple` of two `dict`s mapping the types of sockets used by this simulation element to a dedicated 
                port socket and asynchronous lock pair
        """ 
        if self.__network_activated:
            raise PermissionError('Attempted to configure network after it has already been configurated.')

        self._network_context = azmq.Context()
        external_socket_map = self.__config_external_network()
        internal_socket_map = self.__config_internal_network()

        self.__network_activated = True

        return external_socket_map, internal_socket_map

    def __config_external_network(self) -> dict:
        """
        Initializes and connects essential network port sockets for inter-element communication
        
        #### Returns:
            - `dict` mapping the types of sockets used by this simulation element to a dedicated 
                port socket and asynchronous lock pair
        """
        external_addresses = self._network_config.get_external_addresses()
        external_socket_map = dict()

        for socket_type in external_addresses:
            address = external_addresses[socket_type]
            socket_type : zmq.Socket; address : str

            external_socket_map[socket_type] = self.__socket_factory(socket_type, address)

        return external_socket_map

    def __config_internal_network(self) -> dict:
        """
        Initializes and connects essential network port sockets for intra-element communication
        
        #### Returns:
            - `dict` mapping the types of sockets used by this simulation element to a dedicated 
                port socket and asynchronous lock pair
        """
        internal_addresses = self._network_config.get_internal_addresses()
        internal_socket_map = dict()

        for socket_type in internal_addresses:
            address = internal_addresses[socket_type]
            socket_type : zmq.Socket; address : str

            internal_socket_map[socket_type] = self.__socket_factory(socket_type, address)

        return internal_socket_map

    def __socket_factory(self, socket_type : zmq.SocketType, addresses : list) -> tuple:
        """
        Creates a ZMQ socket of a given type and binds it or connects it to a given address .

        ### Attributes:
            - context (`azmq.Context`): asynchronous network context to be used
            - socket_type (`zmq.SocketType`): type of socket to be generated
            - addresses (`list`): desired addresses to be bound or connected to the socket being generated

        ### Returns:
            - socket (`zmq.Socket`): socket of the desired type and address
            - lock (`asyncio.Lock`): socket lock for asynchronous access

        ### Usage
            socket, lock = socket_factory(context, socket_type, address)
        """

        # create socket
        socket : zmq.Socket = self._network_context.socket(socket_type)

        # connect or bind to network port
        for address in addresses:
            if socket_type in [zmq.PUB, zmq.PUSH, zmq.REP]:
                if self.__is_address_in_use(address):
                    raise ConnectionAbortedError(f'Cannot bind to address {address}. Is currently in use by another process.')
                
                socket.bind(address)

            elif socket_type in [zmq.SUB, zmq.PULL]:
                socket.connect(address)

            else:
                raise NotImplementedError(f'Socket of type {socket_type} not yet supported.')

        # set socket options
        socket.setsockopt(zmq.LINGER, 0)
        if socket_type is zmq.PUB:
            # allow for subscribers to connect to this port
            socket.sndhwm = 1100000

        elif socket_type is zmq.SUB:
            # subscribe to messages addressed to this element or to all elements in the network
            socket.setsockopt(zmq.SUBSCRIBE, self._network_name.encode('ascii'))
            socket.setsockopt(zmq.SUBSCRIBE, self._element_name.encode('ascii'))
            # socket.setsockopt(zmq.SUBSCRIBE, SimulationElementRoles.ALL.value.encode('ascii'))
        
        return (socket, asyncio.Lock())

    def __is_address_in_use(self, address : str) -> bool:
        """
        Checks if an address within `localhost` is already bound to an existing socket.

        ### Arguments:
            - address (`str`): address being evaluated

        ### Returns:
            - `bool`: True if port is already in use
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            address : str
            address_components = address.split(':')
            port = int(address_components[-1])

            return s.connect_ex(('localhost', port)) == 0

    def _deactivate_network(self) -> None:
        """
        Shut down all activated network ports
        """
        # close connections
        for socket_type in self._external_socket_map:
            socket_type : zmq.SocketType
            socket, _ = self._external_socket_map[socket_type]
            socket : zmq.Socket
            socket.close()  

        # close network context
        if self._network_context is not None:
            self._network_context : zmq.Context
            self._network_context.term()  

        self.__network_activated = False

    """
    NETWORK SYNC
    """
    def sync(self) -> tuple:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and become online. 
        
        Elements will then reach out to the manager subscribe to future broadcasts.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports
        and broadcast it to all memebers of the simulation once they all become online. 

        This will signal the beginning of the simulation.

        #### Returns:
            - `tuple` of two `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        async def routine():
            """
            Synchronizes internal and external ports

            ### Returns:
                - `tuple` containing the external and internal address ledgers
            """
            try:
                if self.__network_synced:
                    raise PermissionError('Attempted to sync with network after it has already been synced.')

                # sync internal network
                internal_sync_task = asyncio.create_task(self._internal_sync(), name='Internal Sync Task')
                timeout_task = asyncio.create_task( asyncio.sleep(10) , name='Timeout Task')

                await asyncio.wait([internal_sync_task, timeout_task], return_when=asyncio.FIRST_COMPLETED)
                                
                if timeout_task.done():
                    internal_sync_task.cancel()
                    await internal_sync_task
                    raise TimeoutError('Sync with internal network elements timed out.')
                
                # sync external network
                external_sync_task = asyncio.create_task(self._external_sync(), name='External Sync Task')
                
                await asyncio.wait([external_sync_task, timeout_task], return_when=asyncio.FIRST_COMPLETED)
                
                if timeout_task.done():
                    external_sync_task.cancel()
                    await external_sync_task
                    raise TimeoutError('Sync with external network elements timed out.')

                # log as synced
                self.__network_synced = True

                # return external and internal address ledgers
                return (external_sync_task.result(), internal_sync_task.result())             
                
            except TimeoutError as e:
                self._log(f'Sync aborted. {e}')
                
                # cancel sync subroutine
                if not external_sync_task.done():
                    external_sync_task.cancel()
                    await external_sync_task

                if not external_sync_task.done():
                    external_sync_task.cancel()
                    await external_sync_task

                raise e

        return (asyncio.run(routine()))

    @abstractmethod
    async def _external_sync(self) -> dict:
        """
        Synchronizes with other simulation elements

        #### Returns:
            - `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        pass

    @abstractmethod
    async def _internal_sync(self) -> dict:
        """
        Synchronizes with this element's internal components

        #### Returns:
            - `dict` mapping a simulation element's components' names to the addresses pointing to their respective connecting ports
        """
        pass

    """
    SEND/RECEIVE MESSAGES
    """
    async def __send_msg(self, msg : SimulationMessage, socket_type : zmq.SocketType, socket_map : dict):
        """
        Sends a multipart message to a given socket type.

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - socket_type (`zmq.SocketType`): desired socket type to be used to transmit messages
            - socket_map (`dict`): map of socket types to socket objects and their respective locks
        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        try:
            # get appropriate socket and lock
            socket, socket_lock = None, None
            socket, socket_lock = socket_map.get(socket_type, (None, None))
            socket : zmq.Socket; socket_lock : asyncio.Lock
            acquired_by_me = False
            
            if (socket is None 
                or socket_lock is None):
                raise KeyError(f'Socket of type {socket_type.name} not contained in this simulation element.')
            
            # check socket's message transmition capabilities
            if (
                socket_type != zmq.REQ 
                and socket_type != zmq.REP 
                and socket_type != zmq.PUB 
                and socket_type != zmq.PUSH
                ):
                raise RuntimeError(f'Cannot send messages from a port of type {socket_type.name}.')

            # acquire lock
            self._log(f'acquiring port lock for socket of type {socket_type.name}...')
            await socket_lock.acquire()
            acquired_by_me = True
            self._log(f'port lock for socket of type {socket_type.name} acquired! Sending message...')

            # send multi-part message
            dst : str = msg.dst
            src : str = self.name
            content : str = str(msg.to_json())

            await socket.send_multipart([dst.encode('ascii'), 
                                         src.encode('ascii'), 
                                         content.encode('ascii')])
            self._log(f'message sent! Releasing lock...')
            
            # return sucessful transmission flag
            return True
        
        except asyncio.CancelledError as e:
            print(f'message transmission interrupted. {e}')
            return False

        except Exception as e:
            print(f'message transmission failed. {e}')
            raise e

        finally:
            if (
                socket_lock is not None
                and isinstance(socket_lock, asyncio.Lock) 
                and socket_lock.locked() 
                and acquired_by_me
                ):

                # if lock was acquired by this method and transmission failed, release it 
                socket_lock.release()
                self._log(f'lock released!')

    async def _send_external_msg(self, msg : SimulationMessage, socket_type : zmq.SocketType) -> bool:
        """
        Sends a multipart message to a given socket type for external communication.

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - socket_type (`zmq.SocketType`): desired socket type to be used to transmit messages
        
        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        return await self.__send_msg(msg, socket_type, self._external_socket_map)

    async def _send_internal_msg(self, msg : SimulationMessage, socket_type : zmq.SocketType) -> bool:
        """
        Sends a multipart message to a given socket type for internal communcation.

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - socket_type (`zmq.SocketType`): desired socket type to be used to transmit messages
        
        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        return await self.__send_msg(msg, socket_type, self._internal_socket_map)

    async def __receive_msg(self, socket_type : zmq.SocketType, socket_map : dict) -> list:
        """
        Reads a multipart message from a given socket.

        ### Arguments:
            - socket_type (`zmq.SocketType`): desired socket type to be used to receive a messages

        ### Returns:
            - `list` containing the received information:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the body of the message as `content` (`dict`)
        """
        try:
             # get appropriate socket and lock
            socket, socket_lock = None, None
            socket, socket_lock = socket_map.get(socket_type, (None, None))
            socket : zmq.Socket; socket_lock : asyncio.Lock
            acquired_by_me = False
            
            if (socket is None 
                or socket_lock is None):
                raise KeyError(f'Socket of type {socket_type.name} not contained in this simulation element.')

            # check socket's message transmition capabilities
            if (
                socket_type != zmq.REQ 
                and socket_type != zmq.REP
                and socket_type != zmq.SUB
                and socket_type != zmq.PULL
                ):
                raise RuntimeError(f'Cannot receive a messages from a port of type {socket_type.name}.')

            # acquire lock
            self._log(f'acquiring port lock for socket of type {socket_type.name}...')
            await socket_lock.acquire()
            acquired_by_me = True
            self._log(f'port lock for socket of type {socket_type.name} acquired! Receiving message...')


            # send multi-part message
            b_dst, b_src, b_content = await socket.recv_multipart()
            b_dst : bytes; b_src : bytes; b_content : bytes

            dst : str = b_dst.decode('ascii')
            src : str = b_src.decode('ascii')
            content : dict = json.loads(b_content.decode('ascii'))
            self._log(f'message received from {src} intended for {dst}! Releasing lock...')

            # return received message
            return dst, src, content

        except asyncio.CancelledError as e:
            print(f'message reception interrupted. {e}')
            return
            
        except Exception as e:
            self._log(f'message reception failed. {e}')
            raise e
        
        finally:
            if (
                socket_lock is not None
                and isinstance(socket_lock, asyncio.Lock)
                and socket_lock.locked() 
                and acquired_by_me
                ):

                # if lock was acquired by this method and transmission failed, release it 
                socket_lock.release()
                self._log(f'lock released!')

    async def _receive_external_msg(self, socket_type : zmq.SocketType) -> list:
        """
        Reads a multipart message from a given socket for external communication.

        ### Arguments:
            - socket_type (`zmq.SocketType`): desired socket type to be used to receive a messages

        ### Returns:
            - `list` containing the received information:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the body of the message as `content` (`dict`)

        ### Usage:
            - dst, src, content = await self._receive_external_msg(socket_type)
        """
        return await self.__receive_msg(socket_type, self._external_socket_map)

    async def _receive_internal_msg(self, socket_type : zmq.SocketType) -> list:
        """
        Reads a multipart message from a given socket for internal communication.

        ### Arguments:
            - socket_type (`zmq.SocketType`): desired socket type to be used to receive a messages

        ### Returns:
            - `list` containing the received information:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the body of the message as `content` (`dict`)

        ### Usage:
            - dst, src, content = await self._receive_internal_msg(socket_type)
        """
        return await self.__receive_msg(socket_type, self._internal_socket_map)
