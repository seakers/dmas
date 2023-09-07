from datetime import timedelta
import logging
import math
from dmas.clocks import ClockConfig
from dmas.elements import *
from dmas.utils import *
from tqdm import tqdm

class AbstractManager(SimulationElement):
    """
    ## Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Additional Attributes:
        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration                  
    """
    __doc__ += SimulationElement.__doc__
    
    def __init__(self, 
                simulation_element_name_list : list,
                clock_config : ClockConfig,
                network_config : NetworkConfig,
                level : int = logging.INFO,
                logger : logging.Logger = None
                ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of names of all simulation elements
            - clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
            - network_config (:obj:`NetworkConfig`): description of the addresses pointing to this simulation manager
            - level (`int`): logging level for this simulation element
        """
        super().__init__(SimulationElementRoles.MANAGER.name, network_config, level, logger)
                   
        # check arguments
        if not isinstance(simulation_element_name_list, list):
            raise AttributeError(f'`simulation_element_name_list` must be of type `list`. is of type {type(simulation_element_name_list)}')        
        if not isinstance(clock_config, ClockConfig):
            raise AttributeError(f'`clock_config` must be of type `ClockConfig`. is of type {type(clock_config)}')        
        
        if zmq.REP not in network_config.get_manager_addresses():
            raise AttributeError(f'`network_config` must contain a REP port and an address to parent node within manager address map.')
        if zmq.PUB not in network_config.get_manager_addresses():
            raise AttributeError(f'`network_config` must contain a PUB port and an address to parent node within manager address map.')
        if zmq.PUSH not in network_config.get_manager_addresses():
            raise AttributeError(f'`network_config` must contain a PUSH port and an address to parent node within manager address map.')

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config
        self._manager_address_ledger = {SimulationElementRoles.MANAGER.name : network_config}
        
        # check elements in list
        self._check_element_list()

    @abstractmethod
    def _check_element_list(self):
        """
        Checks the names of the simulation elements given to the manager and confirms all necessary elements are being
        considerd in the simulation.
        """
        pass

    async def _internal_sync(self, _ : ClockConfig) -> dict:
        # no internal modules to sync with
        return None

    async def _external_sync(self) -> tuple:
        # wait for all simulation elements to initialize and connect to me
        external_address_ledger = await self.__wait_for_online_elements()

        await asyncio.sleep(0.1)

        # broadcast address ledger
        self.log('broadcasting simulation information to all elements...')
        sim_info_msg = SimulationInfoMessage(self._network_name, external_address_ledger, self._clock_config.to_dict(), time.perf_counter())
        await self._send_manager_msg(sim_info_msg, zmq.PUB)
        self.log('simulation information sent!')

        await asyncio.sleep(0.1)

        # return clock configuration and external address ledger
        return self._clock_config, external_address_ledger

    async def _wait_sim_start(self) -> None:
        # wait for all elements to be online
        await self.__wait_for_ready_elements()

        await asyncio.sleep(0.1)

    async def _execute(self) -> None:  
        # broadcast simulation start to all simulation elements
        self.log(f'starting simulation for date {self._clock_config.start_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)
        sim_start_msg = SimulationStartMessage(self._network_name, time.perf_counter())
        await self._send_manager_msg(sim_start_msg, zmq.PUB)

        # push simulation start to monitor
        self.log('informing monitor of simulation start...')
        sim_start_msg.dst = SimulationElementRoles.MONITOR.value
        await self._send_manager_msg(sim_start_msg, zmq.PUSH)

        # wait for simulation duration to pass
        self.log('starting simulation timer...')
        timer_task = asyncio.create_task( self.sim_wait(self._clock_config.get_total_seconds()) )
        timer_task.set_name('Simulation timer')
        await timer_task

        # broadcast simulation end
        sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        await self._send_manager_msg(sim_end_msg, zmq.PUB)

        # TODO: allow for simulation to end if all nodes are deactivated before the timer runs out
        self.log(f'Ending simulation for date {self._clock_config.end_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)

    async def _publish_deactivate(self) -> None:
        sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        await self._send_manager_msg(sim_end_msg, zmq.PUSH)
    
    async def __wait_for_elements(self, message_type : NodeMessageTypes, message_class : SimulationMessage = SimulationMessage, desc : str = 'Waiting for simulation elements'):
        """
        Awaits for all simulation elements to share a specific type of message with the manager.
        
        #### Returns:
            - `dict` mapping simulation elements' names to the messages they sent.
        """
        try:
            received_messages = dict()
            read_task = None
            send_task = None

            with tqdm(total=len(self._simulation_element_name_list) , desc=desc, leave=False) as pbar:
                while (
                        len(received_messages) < len(self._simulation_element_name_list) 
                        and len(self._simulation_element_name_list) > 0
                        ):
                    # reset tasks
                    read_task = None
                    send_task = None

                    # wait for incoming messages
                    read_task = asyncio.create_task( self._receive_manager_msg(zmq.REP) )
                    await read_task
                    _, src, msg_dict = read_task.result()
                    msg_type = msg_dict['msg_type']

                    if msg_type != message_type.value:
                        # ignore all incoming messages that are not of the desired type 
                        self.log(f'Received {msg_type} message from node {src}! Ignoring message...')

                        # inform node that its message request was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                        send_task = asyncio.create_task( self._send_manager_msg(msg_resp, zmq.REP) )
                        await send_task

                        continue

                    # unpack and message
                    self.log(f'Received {msg_type} message from node {src}!')
                    msg_req = message_class(**msg_dict)
                    msg_resp = None

                    # log subscriber confirmation
                    if src not in self._simulation_element_name_list and self._element_name + '/' + src not in self._simulation_element_name_list:
                        # node is not a part of the simulation
                        self.log(f'{src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                        # inform agent that its message was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                        print(self._simulation_element_name_list)

                    elif src in received_messages:
                        # node is a part of the simulation but has already communicated with me
                        self.log(f'{src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                        # inform agent that its message request was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                    else:
                        # node is a part of the simulation and has not yet been synchronized
                        received_messages[src] = msg_req
                        pbar.update(1)

                        # inform agent that its message request was not accepted
                        msg_resp = ManagerReceptionAckMessage(src, -1)
                        self.log(f'{src} has now reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # send response
                    send_task = asyncio.create_task( self._send_manager_msg(msg_resp, zmq.REP) )
                    await send_task
                
                return received_messages
        
        except Exception as e:
            self.log(f'wait failed. {e}', level=logging.ERROR)
            raise e

        finally: 
            # cancel read message task in case it is still being performed
            if read_task is not None and not read_task.done(): 
                read_task.cancel()
                await read_task

            # cancel send message task in case it is still being performed
            if send_task is not None and not send_task.done(): 
                send_task.cancel()
                await send_task

    async def __wait_for_online_elements(self) -> dict:
        """
        Awaits for all simulation elements to become online and send their network configuration.
        
        It then compiles this information and creates an external address ledger.

        #### Returns:
            - `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        self.log(f'Waiting for sync requests from simulation elements...')
        desc=f'{self.name}: Syncing simulation elements'
        received_sync_requests = await self.__wait_for_elements(NodeMessageTypes.SYNC_REQUEST, NodeSyncRequestMessage, desc=desc)
        
        self.log(f'All elements synced!')

        external_address_ledger = dict()
        for src in received_sync_requests:
            msg : NodeSyncRequestMessage = received_sync_requests[src]
            external_address_ledger[src] = msg.get_network_config()
        
        return external_address_ledger

    async def __wait_for_ready_elements(self) -> None:
        """
        Awaits for all simulation elements to receive their copy of the address ledgers and process them accordingly.

        Once all elements have reported to the manager, the simulation will begin.
        """
        self.log(f'Waiting for ready messages from simulation elements...')
        desc=f'{self.name}: Ready simulation elements'
        await self.__wait_for_elements(NodeMessageTypes.NODE_READY, NodeReadyMessage, desc=desc)
        self.log(f'All elements ready!')
        return

    async def send_manager_broadcast(self, msg : SimulationMessage) -> None:
        """
        Broadcasts message to all simulation elements currently connected to this manager

        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        return await self._send_manager_msg(msg, zmq.PUB)

    async def listen_for_requests(self):
        """
        Listens for any incoming request message from any simulation element

        ### Returns:
            - `list` containing the received information:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the body of the message as `content` (`dict`)

        ### Usage:
            - dst, src, content = await self._receive_external_msg(socket_type)
        """
        try:
            # reset tasks
            read_task = None

            # wait for incoming messages
            read_task = asyncio.create_task( self._receive_manager_msg(zmq.REP) )
            await read_task
            return read_task.result()

        except asyncio.CancelledError:
            if read_task is not None and not read_task.done():
                read_task.cancel()
                await read_task
    
    async def respond_to_request(self, resp : SimulationMessage):
        """
        Responds to a request message with the appropriate response

        ### Arguments:
            - resp (obj:`SimulationMessage`): response message

        ### Returns:
            - `bool` representing a successful transmission if True or False if otherwise.
        """
        self._send_manager_msg(resp, zmq.REP)
