import asyncio
from beartype import beartype
import zmq
import zmq.asyncio as azmq
from dmas.messages import *
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

    async def _listen(self) -> None:
        try:
            # create poller
            poller = azmq.Poller()
            poller.register(self._sub_socket, zmq.POLLIN)
            poller.register(self._rep_socket, zmq.POLLIN)

            # obtain locks for SUB and REP port sockets
            await self._sub_socket_lock.acquire()
            await self._rep_socket_lock.acquire()

            while True:
                socks = await poller.poll()

                if self._sub_socket in socks:
                    # receive message
                    self._sub_socket : azmq.Socket
                    msg_json = await self._sub_socket.recv_json()

                    # unpack message
                    msg_dict : dict = json.loads(msg_json)
                    msg_type = msg_dict.get('@type', None)

                    if msg_type is not None:
                        if ManagerMessageTypes[msg_type] == ManagerMessageTypes.SIM_END:
                            # manager sent a simulation end message. Terminate process
                            break 

                        else:
                            # send to broadcast handler
                            await self._broadcast_handler(msg_dict)

                if self._rep_socket in socks:
                    # receive message
                    self._rep_socket : azmq.Socket
                    msg_json = await self._rep_socket.recv_json()

                    # unpack message
                    msg_dict : dict = json.loads(msg_json)
                    msg_type = msg_dict.get('@type', None)

                    if msg_type is not None:
                        # send to request handler
                        resp : SimulationMessage = await self._request_handler(msg_dict)
                        dst : str = resp.get_dst()
                        content : str = str(resp.to_json())

                        # send appropriate response
                        await self._rep_socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])

            self._sub_socket_lock.release()
            self._rep_socket_lock.release()

        except asyncio.CancelledError:
            if self._sub_socket_lock.locked():
                self._sub_socket_lock.release()

            if self._rep_socket_lock.locked():
                self._rep_socket_lock.release()

    @abstractmethod
    async def _request_handler(self, msg_dict : dict) -> SimulationMessage:
        """
        Reads and handles incoming request messages. 

        Returns the appropriate response for said requests.
        """
        pass

import time

if __name__ == "__main__":

    async def server(socket : azmq.Socket):
        try:
            while True:
                #  Wait for next request from client
                src, content = await socket.recv_multipart()
                src = src.decode('ascii')
                content = json.loads(content.decode('ascii'))
                print(f"Received request from {src}: {content}")

                #  Do some 'work'
                time.sleep(0.5)

                #  Send reply back to client
                src : str = content['src']
                resp : str = 'hello!'
                socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

        except asyncio.CancelledError:
            return

    async def client(socket : azmq.Socket):
        try:
            print("Connecting to hello world server...") 

            # print(f'Client socket options: {socket.getsockopt_string(zmq.)}')   

            #  Do 10 requests, waiting each time for a response
            for request in range(10):
                dst : str = 'SERVER'
                content_dict = dict()
                content_dict['src'] = 'CLIENT'
                content_dict['dst'] = 'SERVER'
                content_dict['@type'] = 'HELLO WORLD'
                content : str = str(json.dumps(content_dict))

                await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])

                #  Get the reply.
                src, content = await socket.recv_multipart()
                src = src.decode('ascii')
                content = content.decode('ascii')
                print(f"Received reply from {dst}: {content}")

        except asyncio.CancelledError:
            return

    async def main():
        context = azmq.Context()
        rep_socket = context.socket(zmq.REP)
        rep_socket.bind("tcp://*:5555")

        req_socket = context.socket(zmq.REQ)
        req_socket.connect("tcp://localhost:5555")

        print(zmq.REQ.name)

        server_task = asyncio.create_task(server(rep_socket))
        client_task = asyncio.create_task(client(req_socket))

        _, pending = await asyncio.wait([server_task, client_task], return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task : asyncio.Task
            task.cancel()
            await task

    asyncio.run(main())
