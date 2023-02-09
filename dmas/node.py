import asyncio
import logging
import time
from beartype import beartype
import zmq

from dmas.element import SimulationElement
from dmas.messages import *
from dmas.utils import *

class Node(SimulationElement):
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
    
    async def _activate(self) -> None:
        # inititate base network connections 
        await super()._activate()

        # sync with all simulation manager
        self._log('syncing with simulation manager...', level=logging.INFO)
        self._address_ledger = await self._sync()
        self._log('sync complete!', level=logging.INFO)

        # wait for sim start announcement
        self._log('waiting for simulation start broadcast...', level=logging.INFO)
        await self._wait_for_sim_start()
        self._log('simlation started!', level=logging.INFO)

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
        self._sub_socket.connect(self._network_config.get_subscribe_address)

        self._name : str
        all_str : str = str(SimulationElementTypes.ALL.name)
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

    async def _sync(self) -> dict:
        """
        Announces to simulation manager that this node's network connections have become online.

        Waits for manager's address ledger.

        ### Returns:
            - address_ledger (`dict`): ledger mapping simulation node names to port addresses
        """
        try:
            # create sync message
            msg = SyncRequestMessage(self.name, self._network_config)

            # connect to simulation manager
            self._log(f'acquiring port lock for a message of type {type(msg)}...')
            await self._req_socket_lock.acquire()
            self._log(f'port lock acquired!')

            self._log('connecting to simulation manager...')
            self._req_socket.connect(self._network_config.get_manager_address())
            self._log('connection to simulation manager established!')

            while True:
                # submit message to manager
                await self._send_from_socket(msg, self._req_socket, self._req_socket_lock)

                # wait for simulation manager to acknowledge msg
                dst, response = await self._receive_from_socket(self._req_socket, self._req_socket_lock)
                
                response : dict
                resp_type = response.get('@type', None)
                if dst == self.name and resp_type == 'ACK':
                    break
        finally:
            # disconnect from simulation manager
            return

        # self.log(f'Connecting to agent {msg.dst} through port number {port}...',level=logging.DEBUG)
        # self.agent_socket_out.connect(f"tcp://localhost:{port}")
        # self.log(f'Connected to agent {msg.dst}!',level=logging.DEBUG)

        # # submit request
        # self.log(f'Transmitting a message of type {type(msg)} (from {self.name} to {msg.dst})...',level=logging.INFO)
        # await self.agent_socket_out_lock.acquire()
        # self.log(f'Acquired lock.',level=logging.DEBUG)
        # await self.agent_socket_out.send_json(msg_json)
        # self.log(f'{type(msg)} message sent successfully. Awaiting response...',level=logging.DEBUG)
                    
        # # wait for server reply
        # await self.agent_socket_out.recv_json()
        # self.agent_socket_out_lock.release()
        # self.log(f'Received message reception confirmation!',level=logging.DEBUG)      

        # # disconnect socket from destination
        # self.log(f'Disconnecting from agent {msg.dst}...',level=logging.DEBUG)
        # self.agent_socket_out.disconnect(f"tcp://localhost:{port}")
        # self.log(f'Disconnected from agent {msg.dst}!',level=logging.DEBUG)


        # self._log('Connection to environment established!')
        # await self.environment_request_lock.acquire()

        # sync_req = SyncRequestMessage(self.name, EnvironmentModuleTypes.ENVIRONMENT_SERVER_NAME.value, self.agent_port_in, count_number_of_subroutines(self))
        # await self.environment_request_socket.send_json(sync_req.to_json())

        # self.log('Synchronization request sent. Awaiting environment response...')

        # # wait for synchronization reply
        # await self.environment_request_socket.recv()  
        # self.environment_request_lock.release()
        pass

    async def _wait_for_sim_start() -> None:
        """
        Announces to simulation manager that this node has comlpeted its initialization routine 
        and is ready to start the simulation.

        Waits for manager's simulation start broadcast.
        """
        pass

    async def _send_manager_message(self, msg : SimulationMessage):
        try:
            # self._log(f'acquiring port lock for a message of type {type(msg)}...')
            # await self._req_socket_lock.acquire()
            # self._log(f'port lock acquired!')
            
            # self._log(f'connecting to simulation manager...')
            # self._network_config : NodeNetworkConfig
            # self._req_socket.connect(self._network_config.get_manager_address())
            # self._log(f'successfully connected to simulation manager!')

            # self._log(f'sending message of type {type(msg)}...')
            # dst : str = msg.get_dst()
            # content : str = str(msg.to_json())

            # if dst != SimulationElementTypes.MANAGER.value:
            #     raise asyncio.CancelledError('attempted to send a non-manager message to the simulation manager.')
            
            # await self._req_socket.send_multipart([dst, content])
            # self._log(f'message transmitted sucessfully!')
            pass

        except asyncio.CancelledError as e:
            self._log(f'message transmission interrupted. {e}')
            
        except:
            self._log(f'message transmission failed.')
            raise

        finally:
            self._req_socket_lock.release()
            self._log(f'port lock released.')
    
    @abstractmethod
    async def _broadcast_handler(self, msg_dict : dict) -> None:
        """
        Reads and handles broadcast messages 
        """

        pass


import zmq.asyncio as azmq
import multiprocessing as mp
from multiprocessing import Pool, Process

async def server():
    try:
        print('SERVER START')

        context = azmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind("tcp://*:5555")

        m = 0
        while m < 10:
            #  Wait for next request from client
            print('SERVER: waiting on message...')
            dst, content = await socket.recv_multipart()
            dst = dst.decode('ascii')
            content = json.loads(content.decode('ascii'))
            src : str = content['src']
            print(f"SERVER: Received request from {src}: {content}")

            #  Do some 'work'
            await asyncio.sleep(0.5)

            #  Send reply back to client
            src : str = content['src']
            resp : str = 'hello!'
            socket.send_multipart([src.encode('ascii'), resp.encode('ascii')])

            m += 1
        
        print('SERVER DONE')

    except asyncio.CancelledError:
        print ('SERVER INTERRUPTED')
        return

async def client():
    try:
        print("SERVER: Connecting to hello world server...") 
        context = azmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://localhost:5555")
        print("SERVER: Connection established!") 

        #  Do 10 requests, waiting each time for a response
        for _ in range(10):
            dst : str = 'SERVER'
            content_dict = dict()
            content_dict['src'] = 'CLIENT'
            content_dict['dst'] = 'SERVER'
            content_dict['@type'] = 'HELLO WORLD'
            content : str = str(json.dumps(content_dict))

            print(f"CLIENT: sending message to {dst}...")
            await socket.send_multipart([dst.encode('ascii'), content.encode('ascii')])
            print(f"CLIENT: message sent! waiting for reply from {dst}...")

            #  Get the reply.
            src, content = await socket.recv_multipart()
            t = time.perf_counter()
            src = src.decode('ascii')
            content = content.decode('ascii')
                            
            print(f"CLIENT: Received reply from {dst} at {t} [s]: {content}")

    except asyncio.CancelledError:
        print('Client service cancelled.')
        return

def tough_process(n : int = 10000):
    try:
        print(f'CLIENT: starting tough process with n={n}...')
        nums = range(n)
        out = []
        for num in nums:
            out.append(num ** 2)

        print(f'CLIENT: tough process completed! {len(out)}')
        return out
    except:
        print(f'CLIENT: tough process interrupted')

def run_client():
    asyncio.run(client())

async def interrupter(n : float, src : str):
    try:
        await asyncio.sleep(n, src)
        print(f'{src}: INTERRUPTOR TRIGGERED!')
    except asyncio.CancelledError:
        print(f'{src}: interruptor interrupted.')
        return

def run_interruptor(n : float, src : str):
    asyncio.run(interrupter(n, src))

async def client_main():
    print('CLIENT START')

    # t1 = asyncio.create_task(client(), name='client')
    # t2 = asyncio.create_task(multitough(), name='multitough')
    # t3 = asyncio.create_task(interrupter(1), name='interrupter')

    # done, pending = await asyncio.wait([t3], return_when=asyncio.FIRST_COMPLETED)

    # for task in done:
    #     task : asyncio.Task
    #     print(f'{task.get_name()} completed!')

    # for task in pending:
    #     task : asyncio.Task
    #     print(f'cancelling {task.get_name()}...')
    #     task.cancel()
    #     await task
    #     print(f'{task.get_name()} cancelled!')

    # if not t2.done():
    #     print(f'cancelling {t2.get_name()}...')
    #     t2.cancel()
    #     await t2
    #     print(f'{t2.get_name()} cancelled!')
    
    # try:
    #     ctx = mp.get_context('spawn')

    #     p1 = ctx.Process(target=tough_process, args=(10000000,))
    #     p2 = ctx.Process(target=tough_process, args=(10000000,))
    #     p3 = ctx.Process(target=run_client, args=())
    #     p4 = ctx.Process(target=run_interruptor, args=(1,))

    #     # p1.daemon = True
    #     # p1.daemon = True

    #     p1.start()
    #     p2.start()
    #     p3.start()
    #     p4.start()

    #     p4.join()

    # except asyncio.CancelledError: 
    #     print('terminating tough processes!')
    
    # finally:
    #     p1.terminate()
    #     p2.terminate()
    #     p3.terminate()

    #     print('CLIENT DONE')

    pool = mp.Pool()
    
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(tough_process, args = (10000000, ))
    pool.apply_async(run_client, args = ())
    pool.apply(run_interruptor, args = (2, 'CLIENT'))

    pool.terminate()
    pool.join()   

    print('CLIENT DONE')

async def server_main():
    t1 = asyncio.create_task(server(), name='server')
    t2 = asyncio.create_task(interrupter(10, 'SERVER'), name='interruptor')

    done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)

    for task in done:
        task : asyncio.Task
        print(f'SERVER: {task.get_name()} completed!')

    for task in pending:
        task : asyncio.Task
        print(f'SERVER: cancelling {task.get_name()}...')
        task.cancel()
        await task
        print(f'SERVER: {task.get_name()} cancelled!')

def server_run():
    asyncio.run(server_main())

def client_run():
    asyncio.run(client_main())

if __name__ == "__main__":
    # goal: show that listening and actions occur in parallel           
    p1 = Process(target=client_run)
    p2 = Process(target=server_run)  

    p1.start()
    p2.start()

    