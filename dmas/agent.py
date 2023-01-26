from abc import ABC, abstractmethod
import asyncio
import os

import zmq
import zmq.asyncio as azmq
import time
import random 
import logging

from .utils import LoggerTypes

class AbstractAgent(ABC):
    def __init__(self) -> None:
        """
        Creates an instance of an Agent node within the DMAS framework. Agents have the following capabilities:
        -Message peer agents in the network
        -Broadcast messages to peers within the network
        -Sense the simulation environment
        -Message the simulation monitor
       
        """
        super().__init__()

        # self._MNGR_PORT_NUMBER = None
        # self._ENV_PORT_NUMBER = None   
        # self._PEER_RECEIVER_PORT_NUMBER = None
        # self._PEER_BROADCAST_RECEIVER_PORT_NUMBER= None
        # self._MONITOR_PORT_NUMBER = None

        self._MNGR_ADRESS = None
        self._ENV_ADDRESS = None
        self._MONITOR_ADDRESS = None

    async def _activate(self) -> None:
        """
        Initiates and executes commands that are thread-sensitive but that must be performed before the simulation starts.
        This includes but is not limited to:
        -Network connections
        -Environment synchronization
        """
        logging.info(f'Activating agent...')

        # initiate network ports and connect to environment server
        logging.debug('Configuring network ports...')
        await self._network_config()
        logging.debug('Network configuration completed!')

        # confirm online status to environment server 
        logging.debug("Synchronizing with environment...")
        await self.sync_with_simulation()
        logging.debug(f'Synchronization response received! Synchronized with environment.')

        # await for start-simulation message from environment
        logging.debug(f'Waiting for simulation start broadcast...')
        await self.wait_sim_start()
        logging.debug(f'Simulation start broadcast received!')

        logging.info(f'Agent successfully activated!')

    async def _network_config(self):
        """
        Creates communication sockets and connects this agent to the simulation manager, environment, braodcaster, and monitor. 

        '_mngr_socket': listens for broadcasts coming from the simulation manager
        '_env_socket': used to request and receive information directly from the environment
        'agent_socket_in': conects to other agents. Receives requests for information from others
        'agent_socket_out': connects to other agents. Sends information to others
        """
        self._context = azmq.Context() 

        if not self._MNGR_PORT_NUMBER:
            raise Exception("Network config failed. Manager Port Number is required.")
        elif not self._ENV_PORT_NUMBER:
            raise Exception("Network config failed. Environment Port Number is required.")
        elif not self._PEER_RECEIVER_PORT_NUMBER:
            raise Exception("Network config failed. Peer Receiver Port Number is required.")
        elif not self._PEER_BROADCAST_RECEIVER_PORT_NUMBER:
            raise Exception("Network config failed. Peer Broadcast Receiver Port Number is required.")
        elif not self._MONITOR_PORT_NUMBER:
            raise Exception("Network config failed. Simulation Monitor Port Number is required.")

        # Manager broadcast socket
        self._mngr_broadcast_socket = self._context.socket(zmq.SUB)
        self._mngr_broadcast_socket.connect(f"tcp://localhost:{self._MNGR_PORT_NUMBER}")
        self._mngr_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')
        self._mngr_broadcast_socket.setsockopt(zmq.LINGER, 0)

        # give manager time to set up
        time.sleep(random.random())

        # environment socket
        self._env_socket = self._context.socket(zmq.REQ)
        self._env_socket.connect(f"tcp://localhost:{self._ENV_PORT_NUMBER}")
        self._env_socket.setsockopt(zmq.LINGER, 0)
        self._env_request_lock = asyncio.Lock()

        # peer-to-peer communication sockets
        self._peer_in_socket = self._context.socket(zmq.REP)
        self._peer_in_socket.bind(f"tcp://*:{self._PEER_RECEIVER_PORT_NUMBER}")
        self._peer_in_socket.setsockopt(zmq.LINGER, 0)
        self._peer_in_socket_lock = asyncio.Lock()

        self._peer_out_socket = self._context.socket(zmq.REQ)
        self._peer_out_socket.setsockopt(zmq.LINGER, 0)
        self._peer_out_socket_lock = asyncio.Lock()

        # peer broadcast listening socket
        self._peer_broadcast_in_socket = self._context.socket(zmq.SUB)
        self._peer_broadcast_in_socket.connect(f"tcp://localhost:{self._PEER_BROADCAST_RECEIVER_PORT_NUMBER}")
        self._peer_broadcast_in_socket.setsockopt(zmq.SUBSCRIBE, b'')
        self._peer_broadcast_in_socket.setsockopt(zmq.LINGER, 0)

        # monitor publish socket
        self._monitor_out_socket = self._context.socket(zmq.PUSH)
        self._monitor_out_socket.connect(f"tcp://localhost:{self._MONITOR_PORT_NUMBER}")
        self._monitor_out_socket.setsockopt(zmq.LINGER, 0)
        self._monitor_out_socket_lock = asyncio.Lock()

    async def sync_with_simulation(self):
        """
        Sends a synchronization request message to simulation manager server
        """
        # connect to manager
        
        sync_req = SyncRequestMessage(self.name, EnvironmentModuleTypes.ENVIRONMENT_SERVER_NAME.value, self.agent_port_in, count_number_of_subroutines(self))
        await self.environment_request_socket.send_json(sync_req.to_json())

        self.log('Synchronization request sent. Awaiting environment response...')

        # wait for synchronization reply
        await self.environment_request_socket.recv()  
        self.environment_request_lock.release()

    @abstractmethod
    async def _live(self) -> None:
        """
        Runs the behavior of the agent during the simulation.
        Executes event loop for any ayncronous processes within the agent
        """
        pass

    @abstractmethod
    def _shut_down(self) -> None:
        pass

    @abstractmethod
    def _send_peer_message(self, msg, target) -> None:
        pass

    @abstractmethod
    def _broadcast_peer_message(self, msg) -> None:
        pass

    @abstractmethod
    def _sense_environment(self, sense_req) -> None:
        pass

    @abstractmethod
    def _publish_to_montor(self, msg) -> None:
        pass

class Agent(AbstractAgent):
    async def __init__(self) -> None:
        super().__init__()
