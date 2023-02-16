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
        
        # if SimulationElementTypes.ENVIRONMENT.name not in self._simulation_element_name_list:
        #     raise RuntimeError('List of simulation elements must include the simulation environment.')

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
        # wait for all simulation elements to initialize and connect to me
        external_address_ledger = self.__wait_for_online_elements()

        # broadcast address ledger
        sim_info_msg = SimulationInfoMessage(external_address_ledger, self._clock_config, time.perf_counter())
        self._broadcast_message(sim_info_msg)

        # await for all agents to report as ready
        self.__wait_for_ready_elements()

        # broadcast start of simulation to all 
        sim_start_msg = SimulationStartMessage(time.perf_counter())
        self._broadcast_message(sim_start_msg)

        # return external address ledger
        return external_address_ledger

    def __wait_for_elements(self, message_type : NodeMessageTypes, message_class : type):
        """
        Awaits for all simulation elements to share a specific type of message with the manager.
        
        #### Returns:
            - `dict` mapping simulation elements' names to the messages they sent.
        """

        received_messages = dict()

        while (
                len(received_messages) < len(self._simulation_element_name_list) 
                and len(self._simulation_element_name_list) > 0
                ):

            # wait for incoming messages
            src, msg_dict = self._receive_external_msg(zmq.REP)
            msg_type = msg_dict['@type']

            if NodeMessageTypes[msg_type] != message_type:
                # ignore all incoming messages that are not of type Sync Request
                response = dict()
                response['@type'] = 'IGNORED'

                # inform agent that its message request was not accepted
                msg_resp = ReceptionIgnoredMessage(-1)
                self._send_external_msg(msg_resp, zmq.REP)

                continue

            # unpack and sync message
            msg_req = message_class.from_dict(msg_dict)
            self._log(f'Received sync request from node {src}!')

            # log subscriber confirmation
            if src not in self._simulation_element_name_list:
                # node is not a part of the simulation
                self._log(f'Node {src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                # inform agent that its sync request was not accepted
                msg_resp = ReceptionIgnoredMessage(-1)
                self._send_external_msg(msg_resp, zmq.REP)

            elif src in received_messages:
                # node is a part of the simulation but has already been synchronized
                self._log(f'Node {src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                # inform agent that its sync request was not accepted
                msg_resp = ReceptionIgnoredMessage(-1)
                self._send_external_msg(msg_resp, zmq.REP)
            else:
                # node is a part of the simulation and has not yet been synchronized
                received_messages[src] = msg_req

        self._log(f'wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})!', level=logging.INFO)
        return received_messages

    def __wait_for_online_elements(self) -> dict:
        """
        Awaits for all simulation elements to become online and send their network configuration.
        
        It then compiles this information and creates an external address ledger.

        #### Returns:
            - `dict` mapping simulation elements' names to the addresses pointing to their respective connecting ports    
        """
        self._log(f'Waiting for sync requests from simulation elements...')
        received_sync_requests = self.__wait_for_elements(NodeMessageTypes.SYNC_REQUEST, SyncRequestMessage)
        
        external_address_ledger = dict()
        for src in received_sync_requests:
            msg : SyncRequestMessage = received_sync_requests[src]
            external_address_ledger[src] = msg.get_network_config()
        
        self._log(f'All elements online!')
        return external_address_ledger

    def __wait_for_ready_elements(self) -> None:
        """
        Awaits for all simulation elements to receive their copy of the address ledgers and process them accordingly.

        Once all elements have reported to the manager, the simulation will begin.
        """
        self._log(f'Waiting for ready messages from simulation elements...')
        self.__wait_for_elements(NodeMessageTypes.NODE_READY, NodeReadyMessage)
        self._log(f'All elements ready!')

    def _wait_for_deactivation_confirmations(self) -> None:
        """
        Listens for any incoming messages from other simulation elements. Counts how many simulation elements are deactivated.

        Returns when all simulation elements are deactivated.
        """
        self._log(f'Waiting for deactivation confirmation from simulation elements...')
        self.__wait_for_elements(NodeMessageTypes.NODE_DEACTIVATED, NodeDeactivatedMessage)
        self._log(f'All elements deactivated!')

    def _listen(self, kill_switch : threading.Event) -> None:
        if kill_switch.is_set():
            return

        self._wait_for_deactivation_confirmations(self)
        kill_switch.set()
    
    def _live(self, kill_switch : threading.Event) -> None:
        if kill_switch.is_set():
            return

        # wait for simulation duration to pass
        self._clock_config : ClockConfig
        delta = self._clock_config.end_date - self._clock_config.start_date

        self._sim_wait(delta.seconds, kill_switch)
        
        # broadcast sim end message
        if not kill_switch.is_set():
            self._broadcast_message( SimulationEndMessage(time.perf_counter()) )
        
        kill_switch.set()