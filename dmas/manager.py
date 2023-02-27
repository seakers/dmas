import logging
from dmas.clocks import ClockConfig
from dmas.element import *
from dmas.utils import *

class ManagerNetworkConfig(NetworkConfig):
    """
    ## Manager Network Config
    
    Describes the addresses assigned to the simulation manager
    """
    def __init__(self, 
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
        super().__init__(external_address_map=external_address_map)

class Manager(SimulationElement):
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
        
        # check if an environment is contained in the simulation
        # if SimulationElementRoles.ENVIRONMENT.name not in simulation_element_name_list:
        #     raise AttributeError('List of simulation elements must include one simulation environment.')
        # elif simulation_element_name_list.count(SimulationElementRoles.ENVIRONMENT.name) > 1:
        #     raise AttributeError('List of simulation elements includes more than one simulation environment.')
            
        # initialize constants and parameters
        self._simulation_element_name_list = simulation_element_name_list.copy()
        self._clock_config = clock_config

    async def _internal_sync(self) -> dict:
        # no internal modules to sync with
        return None

    async def _external_sync(self) -> dict:
        # wait for all simulation elements to initialize and connect to me
        external_address_ledger = await self.__wait_for_online_elements()

        # broadcast address ledger
        sim_info_msg = SimulationInfoMessage(external_address_ledger, self._clock_config, time.perf_counter())
        await self._send_external_msg(sim_info_msg, zmq.PUB)

        # return external address ledger
        return external_address_ledger

    def _wait_sim_start(self) -> None:
        async def subroutine():
            # await for all agents to report as ready
            await self.__wait_for_ready_elements()

        asyncio.run(subroutine())

    def _execute(self) -> None:        
        async def subroutine():
            # broadcast simulation start to all simulation elements
            self._log(f'Starging simulation for date {self._clock_config.start_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)
            sim_start_msg = SimulationStartMessage(time.perf_counter())
            await self._send_external_msg(sim_start_msg, zmq.PUB)

            # push simulation start to monitor
            await self._send_external_msg(sim_start_msg, zmq.PUSH)

            # wait for simulation duration to pass
            self._clock_config : ClockConfig
            delta = self._clock_config.end_date - self._clock_config.start_date

            timer_task = asyncio.create_task( self._sim_wait(delta.seconds) )
            timer_task.set_name('Simulation timer')

            # wait for all nodes to report as deactivated
            listen_for_deactivated_task = asyncio.create_task( self.__wait_for_offline_elements() )
            listen_for_deactivated_task.set_name('Wait for deactivated nodes')

            await asyncio.wait([timer_task, listen_for_deactivated_task], return_when=asyncio.FIRST_COMPLETED)
            
            # broadcast simulation end
            sim_end_msg = SimulationEndMessage(time.perf_counter())
            await self._send_external_msg(sim_end_msg, zmq.PUB)

            if timer_task.done():
                # nodes may still be activated. wait for all simulation nodes to deactivate
                await listen_for_deactivated_task

            else:                
                # all nodes have already reported as deactivated before the timer ran out. Cancel timer task
                timer_task.cancel()
                await timer_task     
            
            self._log(f'Ending simulation for date {self._clock_config.end_date} (computer clock at {time.perf_counter()}[s])', level=logging.INFO)

        asyncio.run(subroutine())

    def _publish_deactivate(self) -> None:
        async def subroutine():
            # push simulation end to monitor
            sim_end_msg = SimulationEndMessage(time.perf_counter())
            await self._send_external_msg(sim_end_msg, zmq.PUSH)
        
        asyncio.run(subroutine())
    
    async def __wait_for_elements(self, message_type : NodeMessageTypes, message_class : SimulationMessage = SimulationMessage):
        """
        Awaits for all simulation elements to share a specific type of message with the manager.
        
        #### Returns:
            - `dict` mapping simulation elements' names to the messages they sent.
        """
        try:
            received_messages = dict()
            read_task = None
            send_task = None

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
                    msg_resp = ManagerReceptionIgnoredMessage(-1)
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
                    msg_resp = ManagerReceptionIgnoredMessage(-1)

                elif src in received_messages:
                    # node is a part of the simulation but has already communicated with me
                    self._log(f'Node {src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(-1)
                else:
                    # node is a part of the simulation and has not yet been synchronized
                    received_messages[src] = msg_req

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionAckMessage(-1)

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
        received_sync_requests = await self.__wait_for_elements(NodeMessageTypes.SYNC_REQUEST, NodeSyncRequestMessage)
        
        external_address_ledger = dict()
        for src in received_sync_requests:
            msg : NodeSyncRequestMessage = received_sync_requests[src]
            external_address_ledger[src] = msg.get_network_config()

        external_address_ledger[self.name] = self._network_config.to_dict()
        
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

if __name__ == '__main__':
    from datetime import datetime, timezone
    import sys

    print(sys.argv)
    
    response_address = "tcp://*:5558"
    broadcast_address = "tcp://*:5559"
    monitor_address = "tcp://127.0.0.1:55"
    network_config = ManagerNetworkConfig(response_address, broadcast_address, monitor_address)

    start = datetime(2020, 1, 1, 7, 20, 0, tzinfo=timezone.utc)
    end = datetime(2020, 1, 1, 7, 20, 3, tzinfo=timezone.utc)
    clock_config = RealTimeClockConfig(start, end)

    manager = Manager([], clock_config, network_config, level=logging.DEBUG)

    t_o = time.perf_counter()
    manager.run()
    t_f = time.perf_counter()
    
    print(f'RUNTIME = {t_f - t_o}[s]')
