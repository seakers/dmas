from abc import ABC, abstractmethod
import logging
from multiprocessing import Queue
import socket
import time
import zmq
import zmq.asyncio as azmq
import asyncio

from dmas.utils import *
from dmas.messages import *

class SimulationElementStatus(Enum):
    INIT = 'INITIALIZED'
    ACTIVATED = 'ACTIVATED'
    RUNNING = 'RUNNING'
    DEACTIVATED = 'DEACTIVATED'

class SimulationElement(ABC):
    """
    ## Abstract Simulation Element 

    Base class for all simulation elements. This including all agents, environments, simulation managers, and simulation monitors.

    ### Attributes:
        - _name (`str`): The name of this simulation element
        - _status (`Enum`) : Status of the element within the simulation
        - _logger (`Logger`): debug logger

        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration

        - _context (:obj:`zmq.Context()`): network context used for TCP ports to be used by this simulation element
        - _network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
        - _internal_socket_map (`dict`): Map of ports and port locks to be used by this simulation element to communicate with internal processes
        - _internal_address_ledger (`dict`): ledger mapping the addresses pointing to this simulation element's internal communication ports    
        - _external_socket_map (`dict`): Map of ports and port locks to be used by this simulation element to communicate with other simulation elements
        - _external_address_ledger (`dict`): ledger mapping the addresses pointing to other simulation elements' connecting ports    

    +--------------------+                                                                                          
    |   SIM ELEMENTS     |                                                                                          
    +--------------------+                                                                                          
              ^                                                                                                     
              |                                                                                                     
              v                                                                                                     
    +--------------------+                                                                                          
    |   External Ports   |                                                                                          
    |--------------------|                                                                                          
    |ABSTRACT SIM ELEMENT|                                                                                          
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
    def __init__(self, name : str, network_config : NetworkConfig, level : int = logging.INFO) -> None:
        """
        Initiates a new simulation element

        ### Args:
            - name (`str`): The element's name
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation element
            - level (`int`): logging level for this simulation element
        """
        super().__init__()

        self.name = name
        self._status = SimulationElementStatus.INIT
        self._logger : logging.Logger = self.__set_up_logger(level)

        self._clock_config = None     

        self._context = azmq.Context()
        self._network_config = network_config
        self._internal_socket_map = None
        self._internal_address_ledger = None
        self._external_socket_map = None
        self._external_address_ledger = None

    """
    ELEMENT OPERATION METHODS
    """
    def run(self) -> int:
        """
        Main function. Executes this similation element.

        Procedure follows the sequence:
        1. Initiates `activate()` sequence
        2. `listen()` is excecuted concurrently during `live()` procedure. 
        3. `deactivate()` procedure once either the `listen()` or `live()` procedures terminate.

        Returns `1` if excecuted successfully or if `0` otherwise

        Do NOT override
        """
        try:
            # initiate successful completion flag
            out = 0

            # activate simulation element
            self._log('activating...', level=logging.INFO)
            self._activate()

            ## update status to ACTIVATED
            self._status = SimulationElementStatus.ACTIVATED
            self._log('activated! Waiting for simulation to start...', level=logging.INFO)

            # wait for simulatio nstart
            self._wait_sim_start()
            self._log('simulation has started!', level=logging.INFO)

            ## update status to RUNNING
            self._status = SimulationElementStatus.RUNNING

            ## register simulation runtime start
            self._clock_config.set_simulation_runtime_start( time.perf_counter() )

            # start element life
            self._log('living...', level=logging.INFO)
            self._live()
            self._log('living completed!', level=logging.INFO)
            
            out = 1

        finally:
            # deactivate element
            self._log('deactivating...', level=logging.INFO)
            self._deactivate()
            self._log('deactivating completed!', level=logging.INFO)

            # update status to DEACTIVATED
            self._status = SimulationElementStatus.DEACTIVATED
            self._log('`run()` executed properly.') if out == 1 else self._log('`run()` interrupted.')

            #reguster simulation runtime end
            self._clock_config.set_simulation_runtime_end( time.perf_counter() )
            return out

    def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        By default it only initializes network connectivity of the element.

        May be expanded if more capabilities are needed.
        """
        # inititate base network connections 
        self._external_socket_map = self._config_network()

        # synchronize with other elements in the simulation
        self._external_address_ledger = self._sync()     

        # check for correct element activation
        if self._clock_config is None:
            raise RuntimeError(f'{self.name}: Clock config not received during activation.')

        if self._external_socket_map is None:
            raise AttributeError(f'{self.name}: Element communication sockets not activated during activation.')

        elif self._external_address_ledger is None:
            raise RuntimeError(f'{self.name}: Address Ledger not received during activation.')

    @abstractmethod
    def _wait_sim_start(self) -> None:
        """
        Waits for the simulation to start
        """
        pass

    @abstractmethod
    def _live(self) -> None:
        """
        Procedure to be executed by the simulation element during the simulation. 

        Element will deactivate if this method returns.
        """
        pass
    
    def _deactivate(self) -> None:
        """
        Shut down procedure for this simulation entity. 
        Must close all socket connections.
        """
        # inform others of deactivation
        self._publish_deactivate()

        # close connections
        for socket_type in self._external_socket_map:
            socket_type : zmq.SocketType
            socket, _ = self._external_socket_map[socket_type]
            socket : zmq.Socket
            socket.close()  

        # close network context
        if self._context is not None:
            self._context : zmq.Context
            self._context.term()  
    
    """
    ELEMENT CAPABILITY METHODS
    """
    async def _send_external_msg(self, msg : SimulationMessage, socket_type : zmq.SocketType) -> bool:
        """
        Sends a multipart message to a given socket type.

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - socket_type (`zmq.SocketType`): desired socket type to be used to transmit messages
        
        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        try:
            # get appropriate socket and lock
            socket, socket_lock = None, None
            socket, socket_lock = self._external_socket_map.get(socket_type, (None, None))
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
            dst : str = msg.get_dst()
            src : str = self.name
            content : str = str(msg.to_json())

            await socket.send_multipart([dst.encode('ascii'), src.encode('ascii'), content.encode('ascii')])
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

    async def _receive_external_msg(self, socket_type : zmq.SocketType) -> list:
        """
        Reads a multipart message from a given socket.

        ### Arguments:
            - socket_type (`zmq.SocketType`): desired socket type to be used to receive a messages

        ### Returns:
            - `list` containing the received information:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        try:
             # get appropriate socket and lock
            socket, socket_lock = None, None
            socket, socket_lock = self._external_socket_map.get(socket_type, (None, None))
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


    async def _sim_wait(self, delay : float) -> None:
        """
        Simulation element waits for a given delay to occur according to the clock configuration being used

        ### Arguments:
            - delay (`float`): number of seconds to be waited
        # """
        try:
            wait_for_clock = None

            if isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                async def cancellable_wait(delay : float, freq : float):
                    try:
                        await asyncio.sleep(delay / freq)
                    except asyncio.CancelledError:
                        self._log(f'Cancelled sleep of delay {delay / freq} [s]')
                        raise
                    
                self._clock_config : AcceleratedRealTimeClockConfig
                freq = self._clock_config.sim_clock_freq
                wait_for_clock = asyncio.create_task(cancellable_wait(delay, freq))
                await wait_for_clock

            else:
                raise NotImplementedError(f'clock type {type(self._clock_config)} is not yet supported.')
        
        except asyncio.CancelledError:
            if wait_for_clock is not None and not wait_for_clock.done():
                wait_for_clock : asyncio.Task
                wait_for_clock.cancel()
                await wait_for_clock

    """
    HELPING METHODS
    """
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

    def _is_address_in_use(self, address : str) -> bool:
        """
        Checks if an address within `localhost` is already bound to an existing socket.

        ### Arguments:
            - address (`str`): address being evaluated

        ### Returns:
            - `bool`: True if port is already in use
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            address : str
            _, _, port = address.split(':')
            port = int(port)
            return s.connect_ex(('localhost', port)) == 0

    @abstractmethod
    def _config_network(self) -> dict:
        """
        Initializes and connects essential network port sockets for this simulation element. 

        Must be expanded if more connections are needed.
        
        #### Returns:
            - `dict` mapping the types of sockets used by this simulation element to a dedicated 
                port socket and multithreading lock pair
        """
        pass    

    @abstractmethod
    def _sync(self) -> dict:
        """
        Awaits for all other simulation elements to undergo their initialization and activation routines and become online. 
        
        Elements will then reach out to the manager subscribe to future broadcasts.

        The manager will use these incoming messages to create a ledger mapping simulation elements to their assigned ports
        and broadcast it to all memebers of the simulation once they all become online. 

        This will signal the beginning of the simulation.

        #### Returns:
            - `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        pass

    @abstractmethod
    def _publish_deactivate(self) -> None:
        """
        Notifies other elements of the simulation that this element has deactivated and is no longer participating in the simulation.
        """
        pass