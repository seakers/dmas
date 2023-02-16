import logging
from dmas.element import *
from dmas.participant import Participant
from dmas.utils import *


class AbstractManager(Participant):
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
    
    @beartype
    def __init__(self, 
            simulation_element_name_list : list,
            clock_config : ClockConfig,
            network_config : ManagerNetworkConfig,
            level : int = logging.INFO
            ) -> None:
        """
        Initializes and instance of a simulation manager

        ### Arguments
            - simulation_element_name_list (`list`): list of names of all simulation elements
            - clock_config (:obj:`ClockConfig`): description of this simulation's clock configuration
            - network_config (:obj:`ManagerNetworkConfig`): description of the addresses pointing to this simulation manager
            - level (`int`): logging level for this simulation element
        """
        super().__init__(SimulationElementRoles.MANAGER.name, network_config, level)

        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config
        
        # check if an environment is contained in the simulation
        if SimulationElementRoles.ENVIRONMENT.name not in self._simulation_element_name_list:
            raise RuntimeError('List of simulation elements must include the simulation environment.')

        # TODO check if there is more than one environment in the list 

    def _config_network(self) -> list:
        # inherit PUB and SUB ports
        port_list : dict = super()._config_network()

        # direct message response (RES) port 
        ## create socket from context
        self._network_config : ManagerNetworkConfig
        rep_socket : zmq.Socket = self._context.socket(zmq.REP)
        ## bind to address
        peer_in_address : str = self._network_config.get_response_address()
        rep_socket.bind(peer_in_address)
        rep_socket.setsockopt(zmq.LINGER, 0)
        ## create threading lock
        rep_socket_lock = threading.Lock()

        port_list[zmq.REP] = (rep_socket, rep_socket_lock)

        return port_list

    def _sync(self) -> dict:
        async def subroutine():
            # wait for all simulation elements to initialize and connect to me
            external_address_ledger = await self.__wait_for_online_elements()

            # broadcast address ledger
            sim_info_msg = SimulationInfoMessage(external_address_ledger, self._clock_config, time.perf_counter())
            await self._broadcast_message(sim_info_msg)

            # return external address ledger
            return external_address_ledger

        return (asyncio.run(subroutine()))

    def _wait_sim_start(self) -> None:
        async def subroutine():
            # await for all agents to report as ready
            await self.__wait_for_ready_elements()

        asyncio.run(subroutine())

    def _live(self) -> None:        
        async def subroutine():
            # broadcast simulation start to all simulation elements
            sim_start_msg = SimulationStartMessage(time.perf_counter())
            await self._broadcast_message(sim_start_msg)

            # push simulation start to monitor
            await self._push_message(sim_start_msg)

            # wait for simulation duration to pass
            self._clock_config : ClockConfig
            delay = self._clock_config.end_date - self._clock_config.start_date

            timer_task = asyncio.create_task( self._sim_wait(delay) )
            timer_task.set_name('Simulation timer')

            # wait for all nodes to report as deactivated
            listen_for_deactivated_task = asyncio.create_task( self.__wait_for_offline_elements() )
            listen_for_deactivated_task.set_name('Wait for deactivated nodes')

            asyncio.wait([timer_task, listen_for_deactivated_task], return_when=asyncio.FIRST_COMPLETED)
            
            # broadcast simulation end
            sim_end_msg = SimulationEndMessage(time.perf_counter())
            await self._broadcast_message(sim_end_msg)

            if timer_task.done():
                # nodes may still be activated. wait for all simulation nodes to deactivate
                await listen_for_deactivated_task

            else:                
                # all noeds have already reported as deactivated. Cancel timer task
                timer_task.cancel()
                await timer_task()                

        asyncio.run(subroutine())

    def _publish_deactivate(self) -> None:
        async def subroutine():
            # push simulation end to monitor
            sim_end_msg = SimulationEndMessage(time.perf_counter())
            await self._push_message(sim_end_msg)
        
        asyncio.run(subroutine())
    
    async def __wait_for_elements(self, message_type : NodeMessageTypes, message_class : type):
        """
        Awaits for all simulation elements to share a specific type of message with the manager.
        
        #### Returns:
            - `dict` mapping simulation elements' names to the messages they sent.
        """
        try:
            received_messages = dict()

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
                src, msg_dict = read_task.result()
                msg_type = msg_dict['@type']

                if NodeMessageTypes[msg_type] != message_type:
                    # ignore all incoming messages that are not of the desired type 
                    self._log(f'Received {msg_type} message from node {src}! Ignoring message...')

                    # inform node that its message request was not accepted
                    msg_resp = ReceptionIgnoredMessage(-1)
                    send_task = asyncio.create_task( self._send_external_msg(msg_resp, zmq.REP) )
                    await send_task

                    continue

                # unpack and message
                self._log(f'Received {msg_type} message from node {src}! Message accepted!')
                msg_req = message_class.from_dict(msg_dict)
                msg_resp = None

                # log subscriber confirmation
                if src not in self._simulation_element_name_list:
                    # node is not a part of the simulation
                    self._log(f'{src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # inform agent that its message was not accepted
                    msg_resp = ReceptionIgnoredMessage(-1)

                elif src in received_messages:
                    # node is a part of the simulation but has already communicated with me
                    self._log(f'Node {src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # inform agent that its message request was not accepted
                    msg_resp = ReceptionIgnoredMessage(-1)
                else:
                    # node is a part of the simulation and has not yet been synchronized
                    received_messages[src] = msg_req

                    # inform agent that its message request was not accepted
                    msg_resp = ReceptionAckMessage(-1)

                # send response
                send_task = asyncio.create_task( self._send_external_msg(msg_resp, zmq.REP) )
                await send_task

            self._log(f'wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})!', level=logging.INFO)
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
        received_sync_requests = await self.__wait_for_elements(NodeMessageTypes.SYNC_REQUEST, SyncRequestMessage)
        
        external_address_ledger = dict()
        for src in received_sync_requests:
            msg : SyncRequestMessage = received_sync_requests[src]
            external_address_ledger[src] = msg.get_network_config()
        
        self._log(f'All elements online!')
        return external_address_ledger

    async def __wait_for_ready_elements(self) -> None:
        """
        Awaits for all simulation elements to receive their copy of the address ledgers and process them accordingly.

        Once all elements have reported to the manager, the simulation will begin.
        """
        self._log(f'Waiting for ready messages from simulation elements...')
        await self.__wait_for_elements(NodeMessageTypes.NODE_READY, NodeReadyMessage)
        self._log(f'All elements ready!')

    async def __wait_for_offline_elements(self) -> None:
        """
        Listens for any incoming messages from other simulation elements. Counts how many simulation elements are deactivated.

        Returns when all simulation elements are deactivated.
        """
        self._log(f'Waiting for deactivation confirmation from simulation elements...')
        await self.__wait_for_elements(NodeMessageTypes.NODE_DEACTIVATED, NodeDeactivatedMessage)
        self._log(f'All elements deactivated!')
