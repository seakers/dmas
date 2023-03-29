from datetime import timedelta
import logging
import random
from dmas.clocks import ClockConfig
from dmas.element import *
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
        await self._send_manager_msg(sim_start_msg, zmq.PUSH)

        # wait for simulation duration to pass
        self.log('starting simulation timer...')
        timer_task = asyncio.create_task( self._sim_wait(self._clock_config.get_total_seconds()) )
        timer_task.set_name('Simulation timer')
        await timer_task

        # broadcast simulation end
        sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        await self._send_manager_msg(sim_end_msg, zmq.PUB)

        # wait for all nodes to report as deactivated
        listen_for_deactivated_task = asyncio.create_task( self.__wait_for_offline_elements() )
        listen_for_deactivated_task.set_name('Wait for deactivated nodes')
        await listen_for_deactivated_task

        # TODO: allow for simulation to end if all nodes are deactivated before the timer runs out
        # await asyncio.wait([timer_task, listen_for_deactivated_task], return_when=asyncio.FIRST_COMPLETED)
        
        # # broadcast simulation end
        # sim_end_msg = SimulationEndMessage(self._network_name, time.perf_counter())
        # await self._send_external_msg(sim_end_msg, zmq.PUB)

        # if timer_task.done():
        #     # nodes may still be activated. wait for all simulation nodes to deactivate
        #     await listen_for_deactivated_task

        # else:                
        #     # all nodes have already reported as deactivated before the timer ran out. Cancel timer task
        #     timer_task.cancel()
        #     await timer_task     
        
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

            with tqdm(total=len(self._simulation_element_name_list) , desc=desc) as pbar:
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

                    if NodeMessageTypes[msg_type] != message_type:
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
                        self.log(f'{src} has now reported to be online to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # send response
                    send_task = asyncio.create_task( self._send_manager_msg(msg_resp, zmq.REP) )
                    await send_task
                
                return received_messages
        
        except asyncio.CancelledError:            
            return

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

    async def __wait_for_offline_elements(self) -> None:
        """
        Listens for any incoming messages from other simulation elements. Counts how many simulation elements are deactivated.

        Returns when all simulation elements are deactivated.
        """
        self.log(f'Waiting for deactivation confirmation from simulation elements...')
        desc=f'{self.name}: Offline simulation elements'
        await self.__wait_for_elements(NodeMessageTypes.NODE_DEACTIVATED, NodeDeactivatedMessage, desc=desc)
        self.log(f'All elements deactivated!')
        return

    async def _sim_wait(self, delay : float) -> None:
        """
        Simulation element waits for a given delay to occur according to the clock configuration being used

        ### Arguments:
            - delay (`float`): number of seconds to be waited
        # """
        try:
            desc = f'{self.name}: Simulating for {delay}[s]'
            for _ in tqdm (range (10), desc=desc):
                await asyncio.sleep(delay/10)
        
        except asyncio.CancelledError:
            return  