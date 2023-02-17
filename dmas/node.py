
import asyncio
import logging
import random
import zmq
import concurrent.futures
from dmas.element import SimulationElement
from dmas.messages import *
from dmas.modules import InternalModule
from dmas.participant import Participant
from dmas.utils import *

class Node(Participant):
    """
    ## Abstract Simulation Participant 

    Base class for all simulation participants. This including all agents, environment, and simulation manager.


    ### Communications diagram:
    +-----------+---------+       +--------------+
    |           | REQ     |------>|              | 
    |           +---------+       |              |
    | ABSTRACT  | PUB     |------>| SIM ELEMENTS |
    |   SIM     +---------+       |              |
    |PARTICIPANT| SUB     |<------|              |
    |           +---------+       +==============+ 
    |           | PUSH    |------>|  SIM MONITOR |
    +-----------+---------+       +--------------+
    
    """
    __doc__ += SimulationElement.__doc__
    def __init__(self, name: str, network_config: NetworkConfig, modules : list = [], level: int = logging.INFO) -> None:
        super().__init__(name, network_config, level)   
        
        for module in modules:
            if not isinstance(InternalModule):
                raise TypeError(f'elements in `modules` argument must be of type `{InternalModule}`. Is of type {type(module)}.')
        self._modules = modules.copy()

    def _activate(self) -> None:
        super()._activate()

        # check for correct socket initialization
        if self._internal_socket_map is None:
            raise AttributeError(f'{self.name}: Intra-element communication sockets not activated during activation.')

        if self._internal_address_ledger is None:
            raise RuntimeError(f'{self.name}: Internal address ledger not created during activation.')

    def _config_internal_network(self) -> dict:
        super()._config_internal_network()

        if len(self._modules) > 0:
            with concurrent.futures.ThreadPoolExecutor(len(self._modules)) as pool:
                for module in self._modules:
                    module : InternalModule
                    pool.submit(module.config_network, *[])

    async def _external_sync(self):
        # request to sync with the simulation manager
        while True:
            # send sync request from REQ socket
            msg = SyncRequestMessage(self.name, self._network_config)
            dst, src, content = await self._send_external_request_message(msg)
            dst : str; src : str; content : dict
            msg_type = content['@type']

            if (dst != self.name 
                or src != SimulationElementRoles.MANAGER.value 
                or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                
                # if the manager did not acknowledge the sync request, try again later
                await asyncio.wait(random.random())
            else:
                # if the manager acknowledged the sync request, stop trying
                break

        # wait for external address ledger from manager
        while True:
            # listen for any incoming broadcasts through PUB socket
            dst, src, content = await self._receive_external_msg(zmq.SUB)
            dst : str; src : str; content : dict
            msg_type = content['@type']

            if (dst != self.name 
                or src != SimulationElementRoles.MANAGER.value 
                or ManagerMessageTypes[msg_type] != ManagerMessageTypes.SIM_INFO):
                
                # undesired message received. Ignoring and trying again later
                await asyncio.wait(random.random())
            else:
                # if the manager did not acknowledge the sync request, try again later
                msg : SimulationInfoMessage = SimulationInfoMessage.from_dict(content)
                return msg.get_address_ledger()

    def _wait_sim_start(self) -> None:
        async def subroutine():
            # inform manager that I am ready for the simulation to start
            while True:
                # send ready announcement from REQ socket
                msg = NodeReadyMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                    
                    # if the manager did not acknowledge the request, try again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    break

            # wait for message from manager
            while True:
                # listen for any incoming broadcasts through PUB socket
                dst, src, content = await self._receive_external_msg(zmq.SUB)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.SIM_START):
                    
                    # undesired message received. Ignoring and trying again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager did not acknowledge the sync request, try again later
                    return

        # TODO ADD INTERNAL ANNOUNCEMENT 

        async def routine():
            try:
                task = asyncio.create_task(subroutine())
                await asyncio.wait_for(task, timeout=10)
                
            except asyncio.TimeoutError as e:
                self._log(f'Wait for simulation start timed out. Aborting. {e}')
                
                # cancel sync subroutine
                task.cancel()
                await task

                raise e

        return (asyncio.run(routine()))

    def _publish_deactivate(self) -> None:
        async def routine():
            # inform manager that I am deactivated
            while True:
                # send ready announcement from REQ socket
                msg = NodeDeactivatedMessage(self.name)
                dst, src, content = await self._send_external_request_message(msg)
                dst : str; src : str; content : dict
                msg_type = content['@type']

                if (dst != self.name 
                    or src != SimulationElementRoles.MANAGER.value 
                    or ManagerMessageTypes[msg_type] != ManagerMessageTypes.RECEPTION_ACK):
                    
                    # if the manager did not acknowledge the request, try again later
                    await asyncio.wait(random.random())
                else:
                    # if the manager acknowledge the message, stop trying
                    break

            # push deactivate message to monitor
            msg = NodeDeactivatedMessage(self.name)
            dst, src, content = await self._push_external_message(msg)

        return asyncio.run(routine())

    async def _send_request_message(self, msg : SimulationMessage, address_ledger : dict, socket_map : dict) -> list:
        """
        Sends a message through one of this node's request socket

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent
            - address_ledger (`dict`): address ledger containing the destinations address
            - socket_map (`dict`): list mapping de the desired type of socket to a socket contained by the node

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        try:
            # initialize progress trackers
            send_task = None
            receive_task = None

            # get destination's socket address
            dst_address = address_ledger.get(msg.get_dst(), None)
            
            if dst_address is None:
                raise RuntimeError(f'Could not find address for simulation element of name {msg.get_dst()}.')
            
            # connect to destination's socket
            socket, _ = socket_map.get(zmq.REQ, (None, None))
            socket : zmq.Socket
            self._log(f'connecting to {msg.get_dst()} via `{dst_address}`...')
            socket.connect(dst_address)
            self._log(f'connection to {msg.get_dst()} established! Transmitting a message of type {type(msg)}...')

            # transmit message
            send_task = asyncio.create_task( self._send_msg(msg, zmq.REQ, socket_map) )
            await send_task
            self._log(f'message of type {type(msg)} transmitted sucessfully! Waiting for response from {msg.get_dst()}...')

            # wait for response
            receive_task = asyncio.create_task( self._receive_external_msg(zmq.REQ) )
            await receive_task
            self._log(f'response received from {msg.get_dst()}!')

            # disconnect from destination's socket
            socket.disconnect(dst_address)

            return receive_task.result()
        
        except asyncio.CancelledError as e:
            self._log(f'message broadcast interrupted.')
            if send_task is not None and not send_task.done():
                send_task.cancel()
                await send_task
            
            if receive_task is not None and not receive_task.done():
                receive_task.cancel()
                await receive_task

        except Exception as e:
            self._log(f'message broadcast failed.')
            raise e

    async def _send_external_request_message(self, msg : SimulationMessage) -> list:
        """
        Sends a message through this node's external request socket

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        return await self._send_request_message(msg, self._external_address_ledger, self._external_socket_map)
