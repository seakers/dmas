from abc import abstractmethod
from asyncio import CancelledError
from typing import Union
import logging
from messages import *
from utils import *
from modules import Module
from engineering import *

"""
--------------------------------------------------------
 ________  ___  ___  ________  ________       ___    ___ ________  _________  _______   _____ ______      
|\   ____\|\  \|\  \|\   __  \|\   ____\     |\  \  /  /|\   ____\|\___   ___\\  ___ \ |\   _ \  _   \    
\ \  \___|\ \  \\\  \ \  \|\ /\ \  \___|_    \ \  \/  / | \  \___|\|___ \  \_\ \   __/|\ \  \\\__\ \  \   
 \ \_____  \ \  \\\  \ \   __  \ \_____  \    \ \    / / \ \_____  \   \ \  \ \ \  \_|/_\ \  \\|__| \  \  
  \|____|\  \ \  \\\  \ \  \|\  \|____|\  \    \/  /  /   \|____|\  \   \ \  \ \ \  \_|\ \ \  \    \ \  \ 
    ____\_\  \ \_______\ \_______\____\_\  \ __/  / /       ____\_\  \   \ \__\ \ \_______\ \__\    \ \__\
   |\_________\|_______|\|_______|\_________\\___/ /       |\_________\   \|__|  \|_______|\|__|     \|__|
   \|_________|                  \|_________\|___|/        \|_________|                                   

 _____ ______   ________  ________  ___  ___  ___       _______   ________      
|\   _ \  _   \|\   __  \|\   ___ \|\  \|\  \|\  \     |\  ___ \ |\   ____\     
\ \  \\\__\ \  \ \  \|\  \ \  \_|\ \ \  \\\  \ \  \    \ \   __/|\ \  \___|_    
 \ \  \\|__| \  \ \  \\\  \ \  \ \\ \ \  \\\  \ \  \    \ \  \_|/_\ \_____  \   
  \ \  \    \ \  \ \  \\\  \ \  \_\\ \ \  \\\  \ \  \____\ \  \_|\ \|____|\  \  
   \ \__\    \ \__\ \_______\ \_______\ \_______\ \_______\ \_______\____\_\  \ 
    \|__|     \|__|\|_______|\|_______|\|_______|\|_______|\|_______|\_________\
                                                                    \|_________|
--------------------------------------------------------
"""

"""
COMMS
"""
class IridiumCommsSubsystem(SubsystemModule):
    def __init__(self,
                parent_platform_sim: Module, 
                buffer_size: float,
                health: ComponentHealth = ComponentHealth.NOMINAL,
                status: ComponentStatus = ComponentStatus.ON) -> None:
        """
        Represents the communications subsystem in an agent. Can receive and transmit messages between agents.
        parent_platform_sim:
            platform simulation that the subsystem exists in
        buffer_size:
            size of the buffer in bytes
        """
        super().__init__(SubsystemNames.COMMS.value, parent_platform_sim, IridiumCommsSubsystemState, health, status)
        self.submodules = [
                            IridiumTransmitterComponent(self, 1, buffer_size),
                            IridiumReceiverComponent(self, 1, buffer_size)
                            ]

class IridiumCommsSubsystemState(SubsystemState):
    def __init__(self, component_states: dict, health: SubsystemHealth, status: SubsystemStatus):
        super().__init__(SubsystemNames.COMMS.value, IridiumCommsSubsystem, component_states, health, status)

    def from_subsystem(comms : IridiumCommsSubsystem):
        return IridiumCommsSubsystemState(comms.component_states, comms.health, comms.status)

class IridiumTransmitterComponent(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module, 
                average_power_consumption: float, 
                buffer_capacity: float,
                health: ComponentHealth = ComponentHealth.NOMINAL, 
                status: ComponentStatus = ComponentStatus.OFF, 
                f_update: float = 1) -> None:
        """
        Describes a receiver transmitter capable of sending messages to other agents

        parent_subsystem:
            parent comms subsystem
        average_power_consumption:
            average power consumption in [W]
        buffer_capacity:
            size of the buffer in [Mbytes]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        super().__init__(ComponentNames.TRANSMITTER.value, parent_subsystem, IridiumTransmitterState, average_power_consumption, health, status, f_update)
        self.buffer_capacity = buffer_capacity * 1e6
        self.buffer_allocated = 0

    async def activate(self):
        await super().activate()

        self.access_events = dict()

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Processes messages being sent to this component. Only accepts task messages.
        """
        try:
            if msg.dst_module != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                self.log(f'Received internal message intended for {msg.dst_module}. Rerouting message...')
                await self.send_internal_message(msg)

            elif isinstance(msg, ComponentTaskMessage):
                task = msg.get_task()
                self.log(f'Received a task of type {type(task)}!')
                if isinstance(task, ComponentAbortTask):
                    self.aborts.put(task)
                elif isinstance(task, ComponentMaintenanceTask):
                    self.maintenance_tasks.put(task)
                elif isinstance(task, TransmitMessageTask):
                    await self.state_lock.acquire()

                    t_msg = task.msg
                    t_msg_str = t_msg.to_json()
                    t_msg_length = len(t_msg_str.encode('utf-8'))

                    if self.buffer_allocated + t_msg_length <= self.buffer_capacity:
                        self.log(f'Acepted out-going transmission into buffer!')
                        self.tasks.put(task)
                        self.buffer_allocated += t_msg_length
                        self.log(f'Out-going message of length {t_msg_length} now stored in out-going buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                    else:
                        self.log(f'Rejected out-going transmission into buffer.')
                        self.log(f'Out-going buffer cannot store out-going message of length {t_msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarding message...')

                    self.state_lock.release()                   
            
            elif isinstance(msg.content, EnvironmentBroadcastMessage):
                self.log(f'Received an environment event of type {type(msg.content)}!')
                self.environment_events.put(msg.content)

            elif isinstance(msg.content, InterNodeMessage):
                self.log(f'Received an internode message!',level=logging.DEBUG)
                agent_port_dict = self.get_top_module().AGENT_TO_PORT_MAP
                for agent_port in agent_port_dict:
                    agent = agent_port_dict[agent_port]
                    self.log(f'Sending to agent: {agent_port}',level=logging.DEBUG)
                    if(agent_port == "Iridium"):
                        continue
                    inter_node_msg = InterNodeMeasurementRequestMessage("Iridium",agent_port,msg.content)
                    task_msg = TransmitMessageTask(agent,inter_node_msg,1.0)
                    await self.tasks.put(task_msg)
            elif isinstance(msg.content, MeasurementRequest):
                self.log(f'Received an measurement request!',level=logging.INFO)
                agent_port_dict = self.get_top_module().AGENT_TO_PORT_MAP
                for agent_port in agent_port_dict:
                    agent = agent_port_dict[agent_port]
                    task_msg = TransmitMessageTask(agent,msg,1.0)
                    await self.tasks.put(task_msg)
                await self.tasks.put(task_msg)
            else:
                self.log(f'Internal message of type {type(msg)} not yet supported. Discarding message...')
            
        except asyncio.CancelledError:
            return  

    def is_critical(self) -> bool:
        threshold = 0.05
        return super().is_critical() or self.buffer_allocated/self.buffer_capacity > 1-threshold 

    def is_failed(self) -> bool:
        return super().is_failed() or self.buffer_allocated/self.buffer_capacity >= 1

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Performs a task given to this component. 
        Rejects any tasks if the component is in a failure mode of if it is not intended for to be performed by this component. 
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, TransmitMessageTask):
                # create task variables
                wait_for_access_start = None
                transmit_msg = None
                wait_for_access_end = None
                wait_for_access_end_event = None
                wait_for_message_timeout = None
                processes = []
                acquired = None

                # unpackage message
                msg : InterNodeMessage = task.msg
                self.log(f'Right before wait_for_access_start in perform_task',level=logging.DEBUG)
                # wait for access to target node
                #wait_for_access_start = asyncio.create_task( self.wait_for_access_start(msg.dst) )
                #await wait_for_access_start
                self.log(f'Right before create_tasks in perform_task',level=logging.DEBUG)
                # wait for msg to be transmitted successfully or interrupted due to access end or message timeout
                transmit_msg = asyncio.create_task( self.transmit_message(msg) )
                #wait_for_access_end = asyncio.create_task( self.wait_for_access_end(msg.dst) )
                #wait_for_access_end_event = asyncio.create_task( self.access_events[msg.dst].wait_end() ) 
                #wait_for_message_timeout = asyncio.create_task( self.sim_wait(100.0) )
                processes = [transmit_msg] # TODO add waits back: wait_for_access_start, wait_for_access_end, wait_for_access_end_event, wait_for_message_timeout

                _, pending = await asyncio.wait(processes, return_when=asyncio.FIRST_COMPLETED)
                
                # cancel all pending processes
                for pending_task in pending:
                    self.log(f'Cancelling pending processes!',level=logging.DEBUG)
                    pending_task : asyncio.Task
                    pending_task.cancel()
                self.log(f'Cancelled pending processes!',level=logging.DEBUG)

                # remove message from out-going buffer
                # await self.remove_msg_from_buffer(msg)
                # self.access_events.pop(msg.dst)

                # return task completion status                
                if transmit_msg.done():
                    self.log(f'Successfully transmitted message of type {type(msg)} to target \'{msg.dst}\'!',level=logging.INFO)                    
                    return TaskStatus.DONE

                # elif (wait_for_access_end.done() and wait_for_access_end not in pending) or (wait_for_access_end_event.done() and wait_for_access_end_event not in pending):
                #     self.log(f'Access to target \'{msg.dst}\' lost during transmission of message of type {type(msg)}!',level=logging.DEBUG)
                #     raise asyncio.CancelledError

                else:
                    self.log(f'Message of type {type(msg)} timed out!',level=logging.DEBUG)
                    raise asyncio.CancelledError

            else:
                self.log(f'Task of type {type(task)} not yet supported.',level=logging.DEBUG)
                acquired = None 
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.',level=logging.DEBUG)

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # cancel any task that's not yet completed
            # if not wait_for_access_start.done():
            #     wait_for_access_start.cancel()
            #     await wait_for_access_start

            for process in processes:
                if process is not None and isinstance(process, asyncio.Task) and not process.done():
                    process.cancel()
                    await process

            # return task abort status
            return TaskStatus.ABORTED

    async def transmit_message(self, msg: InterNodeMessage):
        try:
            self.log(f'In transmit_message',level=logging.DEBUG)
            # reformat message
            msg.src = self.name
            msg_json = msg.to_json()
            parent_agent = self.get_top_module()
            # connect socket to destination 
            port = parent_agent.AGENT_TO_PORT_MAP[msg.dst]
            self.log(f'Connecting to agent {msg.dst} through port number {port}...',level=logging.DEBUG)
            parent_agent.agent_socket_out.connect(f"tcp://localhost:{port}")
            self.log(f'Connected to agent {msg.dst}!',level=logging.DEBUG)

            # submit request
            self.log(f'Transmitting a message of type {type(msg)} (from {self.name} to {msg.dst})...',level=logging.DEBUG)
            await parent_agent.agent_socket_out_lock.acquire()
            self.log(f'Acquired lock.',level=logging.DEBUG)
            await parent_agent.agent_socket_out.send_json(msg_json)
            self.log(f'{type(msg)} message sent successfully. Awaiting response...',level=logging.DEBUG)
                        
            # wait for server reply
            await parent_agent.agent_socket_out.recv_json()
            parent_agent.agent_socket_out_lock.release()
            self.log(f'Received message reception confirmation!',level=logging.DEBUG)      

            # disconnect socket from destination
            self.log(f'Disconnecting from agent {msg.dst}...',level=logging.DEBUG)
            parent_agent.agent_socket_out.disconnect(f"tcp://localhost:{port}")
            self.log(f'Disconnected from agent {msg.dst}!',level=logging.DEBUG)
        except asyncio.CancelledError:
            self.log(f'asyncio CancelledError in transmit_message',level=logging.DEBUG)
            parent_agent.agent_socket_out_lock.release()
            self.log(f'Released agent_socket_out lock.',level=logging.DEBUG)
            return


    # async def transmit_message(self, msg: InterNodeMessage):
    #     # reformat message
    #     msg.src = self.name
    #     msg_json = msg.to_json()

    #     # connect socket to destination 
    #     port = self.AGENT_TO_PORT_MAP[msg.dst]
    #     self.log(f'Connecting to agent {msg.dst} through port number {port}...')
    #     self.agent_socket_out.connect(f"tcp://localhost:{port}")
    #     self.log(f'Connected to agent {msg.dst}!')

    #     # submit request
    #     self.log(f'Transmitting a message of type {type(msg)} (from {self.name} to {msg.dst})...')
    #     await self.agent_socket_out_lock.acquire()
    #     await self.agent_socket_out.send_json(msg_json)
    #     self.log(f'{type(msg)} message sent successfully. Awaiting response...')
        
    #     # wait for server reply
    #     await self.agent_socket_out.recv()
    #     self.agent_socket_out_lock.release()
    #     self.log(f'Received message reception confirmation!')      

    #     # disconnect socket from destination
    #     self.log(f'Disconnecting from agent {msg.dst}...')
    #     self.agent_socket_out.disconnect(f"tcp://localhost:{port}")
    #     self.log(f'Disconnected from agent {msg.dst}!')

    async def remove_msg_from_buffer(self, msg : InterNodeMessage):
        try:
            self.log(f'Removing message from out-going buffer...',level=logging.DEBUG)
            acquired = await self.state_lock.acquire()

            msg_str = msg.to_json()
            msg_length = len(msg_str.encode('utf-8'))
            if self.buffer_allocated - msg_length >= 0:
                self.buffer_allocated -= msg_length
            else:
                self.buffer_allocated = 0
            self.log(f'Message sucessfully removed from buffer!',level=logging.DEBUG)

            self.state_lock.release()

        except asyncio.CancelledError:
            if acquired:
                self.state_lock.release()
    
    async def wait_for_access_start(self, target : str):
        try:
            self.log(f'In wait_for_access_start in perform_task',level=logging.DEBUG)
            msg = AgentAccessSenseMessage(self.get_top_module().name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            if response is None:
                raise asyncio.CancelledError            
            while not response.result:
                await self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            self.log(f'Response {response} in perform_task',level=logging.DEBUG)
            if target not in self.access_events:
                self.access_events[target] = EventPair()        

            self.access_events[target].trigger_start()
        except asyncio.CancelledError:
            return

    async def wait_for_access_end(self, target : str):
        try:
            msg = AgentAccessSenseMessage(self.get_top_module().name, target)

            response : AgentAccessSenseMessage = await self.submit_environment_message(msg)
            if response is None:
                raise asyncio.CancelledError
            while response.result:
                await self.sim_wait(1/self.UPDATE_FREQUENCY)
                response : AgentAccessSenseMessage = await self.submit_environment_message(msg)

            if target not in self.access_events:
                self.access_events[target] = EventPair()
            self.access_events[target].trigger_end()

        except asyncio.CancelledError:
            return

    async def environment_event_handler(self, event_msg : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received.
        """
        if isinstance(event_msg, AgentAccessEventBroadcastMessage):
            if not event_msg.rise and event_msg.target in self.access_events:
                # an end of access event for a target agent has been recevied

                # fire end of access event
                self.access_events[event_msg].trigger_end()
                
                return True

        return False

class IridiumTransmitterState(ComponentState):
    def __init__(self,
                power_consumed: float, 
                power_supplied: float, 
                buffer_capacity: float,
                buffer_allocated: float,
                health: ComponentHealth, 
                status: ComponentStatus) -> None:
        super().__init__(ComponentNames.TRANSMITTER.value, TransmitterComponent, power_consumed, power_supplied, health, status)
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = buffer_allocated

    def from_component(transmitter: TransmitterComponent):
        return TransmitterState(transmitter.power_consumed, transmitter.power_supplied, transmitter.buffer_capacity, transmitter.buffer_allocated, transmitter.health, transmitter.status)

class IridiumReceiverComponent(ComponentModule):
    def __init__(self, 
                parent_subsystem: Module,
                average_power_consumption: float,
                buffer_capacity: float,
                health: ComponentHealth = ComponentHealth.NOMINAL,
                status: ComponentStatus = ComponentStatus.ON, 
                f_update: float = 1) -> None:
        """
        Describes a radio receiver capable of sending messages to other agents

        parent_subsystem:
            parent comms subsystem
        average_power_consumption:
            average power consumption in [W]
        buffer_capacity:
            size of the buffer in [Mbytes]
        health:
            health of the component
        status:
            status of the component
        f_update:
            frequency of periodic state checks in [Hz]
        """
        super().__init__(ComponentNames.RECEIVER.value, parent_subsystem, IridiumReceiverState, average_power_consumption, health, status, f_update)
        self.buffer_capacity = buffer_capacity * 1e6
        self.buffer_allocated = 0

    async def activate(self):
        await super().activate()

        self.access_events = dict()
        task = ReceiveMessageTransmission()
        await self.tasks.put(task)

    def is_critical(self) -> bool:
        threshold = 0.05
        return super().is_critical() or self.buffer_allocated/self.buffer_capacity > 1-threshold 

    def is_failed(self) -> bool:
        return super().is_failed() or self.buffer_allocated/self.buffer_capacity >= 1

    async def perform_task(self, task: ComponentTask) -> TaskStatus:
        """
        Listens for any incoming transmissions. Needs to be told to start a ReceiveMessageTransmission
        task from its parent subsystem or CNDH subsystem at the beginning of the simulation otherwise
        all messages will not be received
        """
        try:
            # check if component was the intended performer of this task
            if task.component != self.name:
                self.log(f'Component task not intended for this component. Initially intended for component \'{task.component}\'. Aborting task...')
                raise asyncio.CancelledError

            if isinstance(task, ReceiveMessageTransmission):
                acquired = None

                # gain access to incoming agent message port from parent agent
                parent_agent = self.get_top_module()

                await parent_agent.agent_socket_in_lock.acquire()

                while True:
                    msg_dict = None

                    # listen for messages from other agents
                    self.log('Waiting for agent messages...',level=logging.DEBUG)
                    msg_json = await parent_agent.agent_socket_in.recv_json()
                    self.log(f'Agent message received!',level=logging.DEBUG)
                    blank = dict()
                    blank_json = json.dumps(blank)
                    await parent_agent.agent_socket_in.send_json(blank_json)
                    msg = InterNodeMessage.from_json(msg_json)
                    msg_dict = InterNodeMessage.to_dict(msg)

                    # check if message can fit in incoming buffer
                    msg_str = json.dumps(msg_dict)
                    msg_length = len(msg_str.encode('utf-8'))

                    acquired = await self.state_lock.acquire()
                    if self.buffer_allocated + msg_length <= self.buffer_capacity:
                        self.buffer_allocated += msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                        self.state_lock.release()
                        acquired = None
                
                        # handle request
                        msg_type : InterNodeMessageTypes = InterNodeMessageTypes[msg_dict['@type']]

                        if msg_type is InterNodeMessageTypes.PRINT_MESSAGE:
                            # unpack message
                            msg : PrintMessage = PrintMessage.from_dict(msg_dict)
                            
                            # handle message 
                            self.log(f'Received print instruction: \'{msg.content}\'')

                        # elif msg_type is InterNodeMessageTypes.PLANNER_MESSAGE:
                        #     pass
                        elif msg_type is InterNodeMessageTypes.MEASUREMENT_REQUEST:
                            msg : InterNodeMessage = InterNodeMessage.from_dict(msg_dict)
                            self.log(f'Internodemessage type is {msg}',level=logging.DEBUG)
                            ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, msg)
                            self.log(f'Internal message type is {msg.content}',level=logging.DEBUG)
                            self.log(f'Sending measurement request to other agents (hopefully)!',level=logging.DEBUG)
                            await self.send_internal_message(ext_msg) # send measurement request to all other agents
                        # elif msg_type is InterNodeMessageTypes.MEASUREMENT_MESSAGE:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_REQUEST:
                        #     pass
                        # elif msg_type is InterNodeMessageTypes.INFORMATION_MESSAGE:
                        #     pass
                        else:
                            self.log(content=f'Internode message of type {msg_type.name} not yet supported. Discarding message...')

                        acquired = await self.state_lock.acquire()
                        self.buffer_allocated -= msg_length
                        self.log(f'Incoming message of length {msg_length} now stored in incoming buffer (current state: {self.buffer_allocated}/{self.buffer_capacity}).')
                        self.state_lock.release()
                        acquired = None

                    else:
                        self.log(f'Incoming buffer cannot store incoming message of length {msg_length} (current state: {self.buffer_allocated}/{self.buffer_capacity}). Discarding message...')
                    
            else:
                self.log(f'Task of type {type(task)} not yet supported.')
                raise asyncio.CancelledError

        except asyncio.CancelledError:
            self.log(f'Aborting task of type {type(task)}.')
            parent_agent.agent_socket_in_lock.release()

            # release update lock if cancelled during task handling
            if acquired:
                self.state_lock.release()

            # return task abort status
            return TaskStatus.ABORTED

    async def environment_event_handler(self, event_msg : EnvironmentBroadcastMessage) -> bool:
        """ 
        Affects the component depending on the type of event being received.
        """
        if isinstance(event_msg, AgentAccessEventBroadcastMessage):
            if not event_msg.rise and event_msg.target in self.access_events:
                # an end of access event for a target agent has been recevied

                # fire end of access event
                self.access_events[event_msg].trigger_end()
                
                return True

        return False


class IridiumReceiverState(ComponentState):
    def __init__(self, 
                power_consumed: float, 
                power_supplied: float, 
                buffer_capacity: float,
                buffer_allocated: float,
                health: ComponentHealth, status: ComponentStatus) -> None:
        super().__init__(ComponentNames.RECEIVER.value, IridiumReceiverComponent, power_consumed, power_supplied, health, status)
        self.buffer_capacity = buffer_capacity
        self.buffer_allocated = buffer_allocated

    def from_component(receiver: IridiumReceiverComponent):
        return IridiumReceiverState(receiver.power_consumed, receiver.power_supplied, receiver.buffer_capacity, receiver.buffer_allocated, receiver.health, receiver.status)

class IridiumPlatformSim(Module):
    def __init__(self, parent_module : Module) -> None:
        super().__init__(EngineeringModuleParts.IRIDIUM_PLATFORM_SIMULATION.value, parent_module)
        """
        Simulates the agent's platform including all components and subsystems that comprise the agent.
        Can receive instructions via internal messages of type 'PlatformTaskMessage', 'SubsystemTaskMessage',
        or 'ComponentTaskMessage'.
        """
        
        # TODO create list of subsystems based on component list given to the platform
        self.submodules = [
            IridiumCommsSubsystem(self, 1e6)
        ]

    # TODO include internal state routing that kills the platform sim and the agent if a platform-level failure is detected    

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Forwards any task to the command and data handling subsystem
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                # this module is the intended receiver for this message. Handling message
                self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

        except asyncio.CancelledError:
            return

"""
--------------------------------------------------------
 ____                                                                              
/\  _`\                   __                                __                     
\ \ \L\_\    ___      __ /\_\    ___      __     __   _ __ /\_\    ___      __     
 \ \  _\L  /' _ `\  /'_ `\/\ \ /' _ `\  /'__`\ /'__`\/\`'__\/\ \ /' _ `\  /'_ `\   
  \ \ \L\ \/\ \/\ \/\ \L\ \ \ \/\ \/\ \/\  __//\  __/\ \ \/ \ \ \/\ \/\ \/\ \L\ \  
   \ \____/\ \_\ \_\ \____ \ \_\ \_\ \_\ \____\ \____\\ \_\  \ \_\ \_\ \_\ \____ \ 
    \/___/  \/_/\/_/\/___L\ \/_/\/_/\/_/\/____/\/____/ \/_/   \/_/\/_/\/_/\/___L\ \
                      /\____/                                               /\____/
                      \_/__/                                                \_/__/    
 /'\_/`\            /\ \         /\_ \            
/\      \    ___    \_\ \  __  __\//\ \      __   
\ \ \__\ \  / __`\  /'_` \/\ \/\ \ \ \ \   /'__`\ 
 \ \ \_/\ \/\ \L\ \/\ \L\ \ \ \_\ \ \_\ \_/\  __/ 
  \ \_\\ \_\ \____/\ \___,_\ \____/ /\____\ \____\
   \/_/ \/_/\/___/  \/__,_ /\/___/  \/____/\/____/                                                                                                                                                    
--------------------------------------------------------
"""
class IridiumEngineeringModule(Module):
    def __init__(self, parent_agent : Module) -> None:
        super().__init__(AgentModuleTypes.IRIDIUM_ENGINEERING_MODULE.value, parent_agent, [], 1)
        self.submodules = [
            IridiumPlatformSim(self)
        ]

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Forwards any task to the platform simulator
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # this module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                if isinstance(msg, PlatformTaskMessage) or isinstance(msg, SubsystemTaskMessage) or isinstance(msg, ComponentTaskMessage):
                    self.log(f'Received a tasks message. Forwarding to \'{EngineeringModuleParts.PLATFORM_SIMULATION.value}\' for handling.')
                    msg.dst_module = EngineeringModuleParts.PLATFORM_SIMULATION.value
                    await self.send_internal_message(msg)
                else:
                    # this module is the intended receiver for this message. Handling message
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

        except asyncio.CancelledError:
            return