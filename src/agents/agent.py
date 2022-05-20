import logging
import os
from typing import Union

from simpy import AllOf, AnyOf

from src.agents.components.components import *
from src.agents.state import State
from src.planners.actions import *
from src.planners.planner import Planner


class AbstractAgent:
    '''

    '''

    def __init__(self, env, unique_id, component_list=None, planner: Planner = None):
        """
        Abstract agent class.
        :param env: Simulation environment
        :param unique_id: id for agent
        :param component_list: list of components of the agent
        :param planner: planner used by the agent for assigning tasks
        """
        self.results_dir = self.create_results_directory(unique_id)
        self.logger = self.setup_logger(unique_id)

        self.alive = True

        self.env = env
        self.unique_id = unique_id
        self.other_agents = []
        self.component_list = component_list

        self.transmitter = None
        self.receiver = None
        self.on_board_computer = None
        self.power_generator = None
        self.battery = None
        for component in component_list:
            if type(component) == Transmitter:
                self.transmitter = component
            if type(component) == Receiver:
                self.receiver = component
            elif type(component) == OnBoardComputer:
                self.on_board_computer = component
            elif type(component) == PowerGenerator:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component

        if (self.transmitter is None or self.receiver is None or self.on_board_computer is None
                or self.power_generator is None or self.battery is None):
            raise Exception('Agent requires at least one of each of the following components:'
                            ' transmitter, receiver, on-board computer, power generator, and battery')

        self.planner = planner

        self.state = State(self, component_list, env.now)

    def live(self):
        """
        Main function for agent.
        This function cycles through receiving information from other agents and its environment, process
        this information through the agent's planner, and performs the actions instructed by the planner. If a message
        is received or if a critical state is detected by the agent, it will halt any concurrent actions and will
        reassess its actions with its planner.
        :return:
        """
        while self.alive:
            # update planner
            self.planner.update(self.state, self.env.now)
            plan = self.planner.update(self.state, self)

            # perform actions from planner
            tasks, maintenance_actions = self.plan_to_events(plan)
            listening = self.env.process(self.listening())
            system_check = self.env.process(self.system_check())

            # -perform maintenance actions first
            self.perform_maintenance_actions(maintenance_actions)

            # -check if agent is still alive after maintenance actions
            if not self.alive:
                break

            # -performs other actions while listening for incoming
            #  messages and performing system checks
            if len(tasks) > 0:
                yield AllOf(self.env, tasks) | listening | system_check
            else:
                yield listening | system_check

            # -interrupt all actions being performed in case a message
            #  is received or a critical system state is detected
            if listening.triggered or system_check.triggered:
                for task in tasks:
                    if not task.triggered:
                        if listening.triggered:
                            task.interrupt("New message received! Reevaluating plan...")
                        elif system_check.triggered:
                            task.interrupt("WARING - Critical system state reached! Reevaluating plan...")
            if listening.triggered and not system_check.triggered:
                system_check.interrupt("New message received! Reevaluating plan...")
            elif not listening.triggered and system_check.triggered:
                listening.interrupt("WARING - Critical system state reached! Reevaluating plan...")
            elif not listening.triggered and not system_check.triggered:
                system_check.interrupt("Completed all planner tasks! Updating plan...")
                listening.interrupt("Completed all planner tasks! Updating plan...")

    '''
    ==========MAINTENANCE ACTIONS==========
    '''

    def perform_maintenance_actions(self, actions):
        """
        Performs a list of maintenance actions before performing other tasks. Maintenance tasks include actuating
        components, actuating the agent, or deleting previously received messages to clear up space in the internal
        memory of the agent's on-board computer
        :param actions: List of actions to be performed by the agent
        :return:
        """
        for action in actions:
            if type(action) == ActuateAgentAction:
                self.actuate_agent(action)
            elif type(action) == ActuateComponentAction:
                self.actuate_component(action)
            elif type(action) == DeleteMessageAction:
                self.delete_msg(action)
            else:
                raise Exception(f"Maintenance task of type {type(action)} not yet supported.")

            self.planner.completed_action(action, self.env.now)
        if len(actions) > 0:
            self.logger.debug(f'T{self.env.now}:\tCompleted all maintenance actions.')

    def actuate_agent(self, action: ActuateAgentAction):
        """
        Turns agent on or off.
        :param action: Action instruction from the planner indicating the state of the agent
        :return:
        """
        # turn agent on or off
        status = action.status
        self.alive = status

        self.logger.debug(f'T{self.env.now}:\tSetting life status to: {status}')
        if not status:
            self.logger.debug(f'T{self.env.now}:\tKilling agent...')

    def actuate_component(self, action: Union[ActuateComponentAction, ActuatePowerComponentAction]):
        """
        Turns components on and off.
        :param action: Action instruction from the planner indicating which component to actuate
        :return:
        """
        # actuate component described in action
        component_actuate = action.component
        status = action.status

        for component in self.component_list:
            if component == component_actuate:
                if type(action) == ActuatePowerComponentAction:
                    power = action.power
                    if status:
                        component.turn_on_generator(power)
                        self.logger.debug(f'T{self.env.now}:\tTurning on {component.name}.')
                    else:
                        component.turn_off_generator()
                        self.logger.debug(f'T{self.env.now}:\tTurning off {component.name}.')
                    break
                else:
                    if status:
                        component.turn_on()
                        self.logger.debug(f'T{self.env.now}:\tTurning on {component.name}.')
                    else:
                        component.turn_off()
                        self.logger.debug(f'T{self.env.now}:\tTurning off {component.name}.')
                    break

    def delete_msg(self, action: DeleteMessageAction):
        """
        Deletes a message from the agent's internal on-board memory
        :param action:
        :return:
        """
        # remove message from on-board memory and inform planner
        msg = action.msg
        self.on_board_computer.data_stored.get(msg.size)
        self.planner.message_deleted(msg, self.env.now)

        self.logger.debug(f'T{self.env.now}:\tDeleted message of size {msg.size}')

    def turn_on_components(self, component_list):
        for component in component_list:
            actuate_action = ActuateComponentAction(component, self.env.now, status=True)
            self.actuate_component(actuate_action)

    def turn_off_components(self, component_list):
        for component in component_list:
            actuate_action = ActuateComponentAction(component, self.env.now, status=False)
            self.actuate_component(actuate_action)

    '''
    ==========TASK ACTIONS==========
    '''

    def measure(self, action: MeasurementAction):
        """
        Performs a measurement of a given ground point.
        :param action: Action instruction from the planner indicating what measurement to perform with which instruments
        :return:
        """
        try:
            self.logger.debug(f'T{self.env.now}:\tPreparing form measurement...')

            # un package measurement information
            instrument_list = action.instrument_list
            target = action.target

            # turn on components, collect information, and turn off components
            self.turn_on_components(instrument_list)
            self.logger.debug(f'T{self.env.now}:\tAll instruments ready for measurement. Starting measurement...')

            yield self.env.timeout(action.end - action.start)
            self.logger.debug(f'T{self.env.now}:\tCompleted measurement successfully!')

            self.turn_off_components(instrument_list)
            self.logger.debug(f'T{self.env.now}:\tTurned off all instruments used measurement.')

            # process captured data
            # TODO ADD MEASUREMENT RESULTS TO PLANNER KNOWLEDGE BASE:
            #   results = measurementSimulator(target, instrument_list)
            #   planner.update_knowledge_base(measurement_results=results)

            # inform planner of task completion
            self.planner.completed_action(action, self.env.now)

            # update system status
            return self.update_system()
        except simpy.Interrupt:
            # measurement interrupted
            instrument_list = action.instrument_list
            self.turn_off_components(instrument_list)
            self.planner.interrupted_action(action, self.env.now)
            self.logger.debug(f'T{self.env.now}:\tMeasurement interrupted. '
                              f'Turning off all instruments and waiting for further instructions.')

    def transmit(self, action: TransmitAction):
        """
        Sends a message to another agent. The method forwards a copy of the message to its outgoing buffer and waits to
        establish communications channels with the receiver agent. Once established it will start the transmission. The
        method keeps track of the time between the start and end of the transmission. If the transmission takes longer
        than the predetermined message timeout period, it will stop the transmission and drop the packet.

        :param action: Action instruction from the planner indicating what message will be transmitted
        :return:
        """
        self.logger.debug(f'T{self.env.now}:\tPreparing form transmission...')

        msg = action.msg

        msg_timeout = self.env.process(self.env.timeout(msg.timeout))
        msg_transmission = self.env.process(self.transmitter.send_message(self.env, msg, self.logger))

        # TODO ADD CONTACT-TIME RESTRICTIONS TO SEND MESSAGE
        #   wait_for_access = env.timeout(self.orbit_data.next_access(msg.dst) - self.env.now)
        #   yield wait_for_access | timeout
        #   only continue if wait is done but not timeout

        yield msg_timeout | msg_transmission

        if msg_timeout.triggered and not msg_transmission.triggered:
            self.logger.debug(f'T{self.env.now}:\tMessage transmission timed out.')
            msg_transmission.interrupt("Message transmission timed out. Dropping packet")
            self.planner.interrupted_message(msg, self.env.now)
        elif msg_transmission.triggered:
            self.transmitter.data_rate -= msg.data_rate
            if self.transmitter.channels.count == 0:
                self.transmitter.turn_off()

            self.planner.message_received(msg, self.env.now)
            self.logger.debug(f'T{self.env.now}:\tMessage transmitted successfully!')

            if not msg_timeout:
                msg_timeout.interrupt("Message transmitted successfully!")

        # integrate current state
        self.update_system()

    def charge(self, action: ChargeAction):
        """
        Turns on battery charge status. This will inform update_system() to re-route any excess power being generated
        into the battery so it may be charged at every time-step.
        :param action: Action instruction from the planner indicating start and end time to charging procedure
        :return:
        """
        try:
            self.battery.charging = True
            self.env.timeout(action.end - action.start)
            self.battery.charging = False

            # integrate current state
            return self.update_system()
        except simpy.Interrupt:
            self.battery.charging = False
            self.planner.interrupted_action(action, self.env.now)

    '''
    ==========BACKGROUND ACTIONS==========
    '''

    def listening(self):
        """
        Background tasks that listens for incoming messages. Once a header file is received, it will wait for the rest
        of the message to be received in its incoming buffer so it can pass it to the agent's internal memory. The
        method will wait if there is no memory available in the internal memory. If the wait time goes over a message's
        timeout period it will drop said packet to make room for other incoming packets.
        :return:
        """
        if len(self.transmitter.received_messages) > 0:
            msg = self.transmitter.received_messages.pop()
        else:
            msg = (yield self.receiver.inbox.get())

        msg_timeout = self.env.process(self.env.timeout(msg.timeout))
        msg_reception = self.env.process(self.receiver.receive(self.env, msg, self.on_board_computer, self.logger))

        yield msg_timeout | msg_reception

        if msg_timeout.triggered and not msg_reception.triggered:
            msg_reception.interrupt("Message reception timed out. Dropping packet")
        if msg_reception.triggered:
            self.planner.measurement_received(msg)
            if not msg_timeout.triggered:
                msg_timeout.interrupt("Message successfully received!")

        return

    def system_check(self):
        """
        Background task that checks the agent's system every second. If it detects that the agent is in a critical
        state, it will terminate and inform the agent, forcing it to reevaluate its state and ask the planner how it
        should react to the system state.
        If the planner is unable to fix the critical state, this method will order the agent to deactivate and end its
        mission.
        :return:
        """
        while True:
            # check if system state is critical
            if self.is_in_critical_state():
                if self.state.is_critical():
                    # if state is still critical after planner changes, kill agent
                    kill = ActuateAgentAction(self.env.now, status=False)
                    self.actuate_agent(kill)
                else:
                    self.state.critical = True
                break
            else:
                self.state.critical = False

            # wait 1 second and continue
            yield self.env.timeout(1)

            # integrate current state at new time
            self.update_system()

    def update_system(self):
        """
        Updates the amount of data and energy stored in the on-board computer, transmitter and receiver buffers,
        and battery. Sums the rates coming in for both data and power and integrates using the last state's time and
        the current time to determine the time-step of integration.
        Once this agent's components have been updated, it records this state in the agent's state property.
        :return:
        """
        # count power and data usage
        data_rate_in = 0
        power_out = 0
        power_in = 0
        for component in self.component_list:
            if component.is_on():
                if component.power <= 0:
                    power_out -= component.power
                if type(component) != Receiver and type(component) != Transmitter:
                    data_rate_in += component.data_rate
                if type(component) == Receiver and type(component) == Transmitter:
                    power_in += component.power
        power_dif = power_in - power_out

        # calculate time-step
        dt = self.env.now - self.state.get_last_update_time()

        # update values
        # -data
        if data_rate_in > 0:
            yield self.on_board_computer.data_stored.put(data_rate_in * dt)
        if self.transmitter.data_rate > 0:
            yield self.transmitter.data_stored.get(self.transmitter.data_rate * dt)

        # -power
        power_charging = 0
        if self.battery.is_charging() and power_dif >= 0:
            power_charging += power_dif
        if self.battery.is_on():
            power_charging -= self.battery.power

        if power_charging > 0:
            self.battery.energy_stored.put(power_charging * dt)
        elif power_charging < 0:
            self.battery.energy_stored.get(power_charging * dt)

        # update in state tracking
        self.state.update(self, self.component_list, self.env.now)

    def is_in_critical_state(self):
        """
        Checks if current state is a critical state. Checks for batteries being below their maximum depth-of-discharge
        or being overcharged, checks to see if power is being properly supplied to other components, and checks if there
        is a memory overflow in the internal memory.
        :return:
        """
        data_rate_in, data_rate_out, data_rate_tot, \
        data_buffer_in, data_buffer_out, data_memory, data_capacity, \
        power_in, power_out, power_tot, energy_stored, energy_capacity, \
        t, critical = self.state.get_latest_state()

        if (1 - self.battery.energy_stored.level / self.battery.energy_capacity) > self.battery.dod:
            # battery has reached its maximum depth-of-discharge level
            return True
        elif self.battery.energy_stored.level == self.battery.energy_capacity and self.battery.is_on():
            # battery is full and is still charging
            return True
        elif power_tot < 0:
            # insufficient power being generated
            return True
        elif power_tot > 0 and not self.battery.is_on():
            # excess power being generated and not being used for charging
            return True
        elif self.on_board_computer.data_stored.level == self.on_board_computer.data_capacity and data_rate_in > 0:
            # on-board memory full and data is coming in faster than it is leaving
            return True

        return False

    def set_other_agents(self, others):
        """
        Gives the agent a list of all of the other agents that exist in this simulation
        :param others: list of other agents
        :return:
        """
        for other in others:
            if other is not self:
                self.other_agents.append(other)

    '''
    MISCELANEOUS HELPING METHODS
    '''

    def create_results_directory(self, unique_id):
        """
        Creates a results directory for this particular scenario if it has not been created yet. Initializes a new
        logger report for this particular agent
        :param unique_id: agent's unique ID
        :return:
        """
        directory_path = os.getcwd()
        results_dir = directory_path + '/results/'

        if not os.path.isdir(results_dir):
            os.mkdir(results_dir)

        if os.path.exists(results_dir + f'Agent{unique_id}.log'):
            os.remove(results_dir + f'Agent{unique_id}.log')

        return results_dir

    def setup_logger(self, unique_id):
        """
        Sets up logger for this agent
        :param unique_id: agent's unique ID
        :return:
        """
        logger = logging.getLogger(f'A{unique_id}')
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(name)s-%(message)s')

        file_handler = logging.FileHandler(self.results_dir + f'Agent{unique_id}.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger

    def plan_to_events(self, actions):
        """
        Converts planner actions to executable events
        :param actions: list of actions to be performed
        :return:
        """
        events = []
        maintenance = []
        for action in actions:
            action_event = None
            mnt_event = None
            if type(action) == ActuateAgentAction:
                mnt_event = action
            elif type(action) == ActuateComponentAction:
                mnt_event = action
            elif type(action) == DeleteMessageAction:
                mnt_event = action

            elif type(action) == MeasurementAction:
                action_event = self.env.process(self.measure(action))
            elif type(action) == TransmitAction:
                action_event = self.env.process(self.transmit(action))
            elif type(action) == ChargeAction:
                action_event = self.env.process(self.charge(action))

            if action_event is not None:
                events.append(action_event)
            if mnt_event is not None:
                maintenance.append(mnt_event)

        return events, maintenance
