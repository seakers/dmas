from datetime import timedelta
import logging
import random
from dmas.clocks import ClockConfig
from dmas.element import *
from dmas.utils import *
from tqdm import tqdm

class ManagerNetworkConfig(NetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager
    """
    def __init__(self, 
                network_name : str,
                response_address : str,
                broadcast_address: str,
                monitor_address: str
                ) -> None:
        """
        Initializes an instance of a Manager Network Config Object
        
        ### Arguments:
        - response_address (`str`): a manager's response port address
        - broadcast_address (`str`): a manager's broadcast port address
        - monitor_address (`str`): the simulation's monitor port address
        """
        external_address_map = {zmq.REP: [response_address], 
                                zmq.PUB: [broadcast_address], 
                                zmq.PUSH: [monitor_address]}
        super().__init__(network_name, external_address_map=external_address_map)

class AbstractManager(SimulationElement):
    """
    ## Simulation Manager Class 
    
    Regulates the start and end of a simulation. 
    
    May inform other simulation elements of the current simulation time

    ### Additional Attributes:
        - _simulation_element_list (`list`): list of the names of all simulation elements
        - _clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
        

    ### Communications diagram:
    +------------+---------+                
    |            | REP     |<---->>
    | SIMULATION +---------+       
    |   MANAGER  | PUB     |------>
    |            +---------+       
    |            | PUSH    |------>
    +------------+---------+             
    """
    __doc__ += SimulationElement.__doc__
    
    def __init__(self, 
                simulation_element_name_list : list,
                clock_config : ClockConfig,
                network_config : ManagerNetworkConfig,
                level : int = logging.INFO,
                logger : logging.Logger = None
                ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of names of all simulation elements
            - clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - level (`int`): logging level for this simulation element
        """
        super().__init__(SimulationElementRoles.MANAGER.name, network_config, level, logger)
                   
        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config

    @abstractmethod
    def _check_element_list(self):
        """
        Checks the names of the simulation elements given to the manager and confirms all necessary elements are being
        considerd in the simulation.
        """
        pass

    async def _internal_sync(self) -> dict:
        # no internal modules to sync with
        return None

    async def _external_sync(self) -> dict:
        # wait for all simulation elements to initialize and connect to me
        external_address_ledger = await self.__wait_for_online_elements()

        await asyncio.sleep(0.1)

        # broadcast address ledger
        self._log('broadcasting simulation information to all elements...')
        sim_info_msg = SimulationInfoMessage(self._network_name, external_address_ledger, self._clock_config.to_dict(), time.perf_counter())
        # self._log(sim_info_msg.to_dict())
        await self._send_external_msg(sim_info_msg, zmq.PUB)
        self._log('simulation information sent!')

        await asyncio.sleep(0.1)

        # return clock configuration and external address ledger
        return self._clock_config, external_address_ledger

    async def _wait_sim_start(self) -> None:
        # wait for all elements to be online
        await self.__wait_for_ready_elements()

        await asyncio.sleep(0.1)

    async def cancellable_wait(self, dt):
        try:
            desc = f'{self.name}: Simulating for {dt}[s]'
            for _ in tqdm (range (10), desc=desc):
                await asyncio.sleep(dt/10)
        
        except asyncio.CancelledError:
            return  

    async def _execute(self) -> None:  
        # broadcast simulation start to all simulation elements
        self._log(f'starting simulation for date {self._clock_config.start_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)
        sim_start_msg = SimulationStartMessage(self._network_name, time.perf_counter())
        await self._send_external_msg(sim_start_msg, zmq.PUB)

        # push simulation start to monitor
        self._log('informing monitor of simulation start...')
        await self._send_external_msg(sim_start_msg, zmq.PUSH)

        # wait for simulation duration to pass
        self._log('starting simulation timer...')
        timer_task = asyncio.create_task( self.cancellable_wait(self._clock_config.get_total_seconds()) )
        timer_task.set_name('Simulation timer')

        # wait for all nodes to report as deactivated
        listen_for_deactivated_task = asyncio.create_task( self.__wait_for_offline_elements() )
        listen_for_deactivated_task.set_name('Wait for deactivated nodes')

        await asyncio.wait([timer_task, listen_for_deactivated_task], return_when=asyncio.FIRST_COMPLETED)
        
        # broadcast simulation end
        sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        await self._send_external_msg(sim_end_msg, zmq.PUB)

        if timer_task.done():
            # nodes may still be activated. wait for all simulation nodes to deactivate
            await listen_for_deactivated_task

        else:                
            # all nodes have already reported as deactivated before the timer ran out. Cancel timer task
            timer_task.cancel()
            await timer_task     
        
        self._log(f'Ending simulation for date {self._clock_config.end_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)

    async def _publish_deactivate(self) -> None:
        sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        await self._send_external_msg(sim_end_msg, zmq.PUSH)
    
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

            with tqdm(total=len(self._simulation_element_name_list) , desc=desc) as pbar:
                while (
                        len(received_messages) < len(self._simulation_element_name_list) 
                        and len(self._simulation_element_name_list) > 0
                        ):
                    # reset tasks
                    read_task = None
                    send_task = None

                    # wait for incoming messages
                    read_task = asyncio.create_task( self._receive_external_msg(zmq.REP) )
                    await read_task
                    dst, src, msg_dict = read_task.result()
                    msg_type = msg_dict['msg_type']

                    if NodeMessageTypes[msg_type] != message_type:
                        # ignore all incoming messages that are not of the desired type 
                        self._log(f'Received {msg_type} message from node {src}! Ignoring message...')

                        # inform node that its message request was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                        send_task = asyncio.create_task( self._send_external_msg(msg_resp, zmq.REP) )
                        await send_task

                        continue

                    # unpack and message
                    self._log(f'Received {msg_type} message from node {src}! Message accepted!')
                    msg_req = message_class(**msg_dict)
                    msg_resp = None

                    # log subscriber confirmation
                    if src not in self._simulation_element_name_list:
                        # node is not a part of the simulation
                        self._log(f'{src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                        # inform agent that its message was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)

                    elif src in received_messages:
                        # node is a part of the simulation but has already communicated with me
                        self._log(f'Node {src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                        # inform agent that its message request was not accepted
                        msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                    else:
                        # node is a part of the simulation and has not yet been synchronized
                        received_messages[src] = msg_req
                        pbar.update(1)

                        # inform agent that its message request was not accepted
                        msg_resp = ManagerReceptionAckMessage(src, -1)
                        self._log(f'Node {src} has now reported to be online to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # send response
                    send_task = asyncio.create_task( self._send_external_msg(msg_resp, zmq.REP) )
                    await send_task
                
                return received_messages
        
        except asyncio.CancelledError:            
            return

        except Exception as e:
            self._log(f'wait failed. {e}', level=logging.ERROR)
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
        self._log(f'Waiting for sync requests from simulation elements...')
        desc=f'{self.name}: Online simulation elements'
        received_sync_requests = await self.__wait_for_elements(NodeMessageTypes.SYNC_REQUEST, NodeSyncRequestMessage, desc=desc)
        
        self._log(f'All elements online!')

        external_address_ledger = dict()
        for src in received_sync_requests:
            msg : NodeSyncRequestMessage = received_sync_requests[src]
            external_address_ledger[src] = msg.get_network_config()

        external_address_ledger[self.name] = self._network_config.to_dict()
        
        return external_address_ledger

    async def __wait_for_ready_elements(self) -> None:
        """
        Awaits for all simulation elements to receive their copy of the address ledgers and process them accordingly.

        Once all elements have reported to the manager, the simulation will begin.
        """
        self._log(f'Waiting for ready messages from simulation elements...')
        desc=f'{self.name}: Ready simulation elements'
        await self.__wait_for_elements(NodeMessageTypes.NODE_READY, NodeReadyMessage, desc=desc)
        self._log(f'All elements ready!')

    async def __wait_for_offline_elements(self) -> None:
        """
        Listens for any incoming messages from other simulation elements. Counts how many simulation elements are deactivated.

        Returns when all simulation elements are deactivated.
        """
        self._log(f'Waiting for deactivation confirmation from simulation elements...')
        desc=f'{self.name}: Offline simulation elements'
        await self.__wait_for_elements(NodeMessageTypes.NODE_DEACTIVATED, NodeDeactivatedMessage, desc=desc)
        self._log(f'All elements deactivated!')

class SimulationManager(AbstractManager):
    def _check_element_list(self):
        # check if an environment is contained in the simulation
        if SimulationElementRoles.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise AttributeError('List of simulation elements must include one simulation environment.')
        
        elif SimulationElementRoles.MONITOR.name not in self._simulation_element_name_list:
            raise AttributeError('List of simulation elements must include one simulation monitor.')
        
        elif self._simulation_element_name_list.count(SimulationElementRoles.ENVIRONMENT.name) > 1:
            raise AttributeError('List of simulation elements includes more than one simulation environment.')