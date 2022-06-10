import logging
import os
from typing import Union

import numpy as np
import simpy
from simpy import AllOf, AnyOf

from src.agents.components.components import *
from src.agents.models.systemModel import StatePredictor
from src.agents.state import StateHistory
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
        self.plan = simpy.Store(self.env)
        self.actions = []

        # self.state = State(self, component_list, env.now)
        self.state_history = StateHistory(self, component_list, env.now)
        self.state_predictor = StatePredictor()
        self.critical_state = env.event()

    def live(self):
        """
        Main function for agent.
        This function cycles through receiving information from other agents and its environment, process
        this information through the agent's planner, and performs the actions instructed by the planner. If a message
        is received or if a critical state is detected by the agent, it will halt any concurrent actions and will
        reassess its actions with its planner.
        :return:
        """
        try:
            # initialize background tasks
            self.env.process(self.periodical_systems_check())
            listening = self.env.process(self.listening())
            planner_wait = self.env.process(self.wait_for_plan())

            while self.alive:
                self.logger.debug(f'T{self.env.now}:\tSTARTING IDLE PHASE...')

                # update planner and wait for instructions, an incoming message, or a critical state to be detected
                self.planner.update(self.state_history.get_latest_state(), self.env.now)

                yield planner_wait | listening | self.critical_state

                self.logger.debug(f'T{self.env.now}:\tIDLE PHASE COMPLETE!')

                if planner_wait.triggered:
                    self.logger.debug(f'T{self.env.now}:\tSTARTING DOING PHASE...')

                    # read instructions from planner
                    tasks, maintenance_actions = self.plan_to_events()

                    # # perform manual systems check prior to any actions
                    # self.systems_check()

                    # perform maintenance actions
                    self.perform_maintenance_actions(maintenance_actions)

                    # perform manual systems check
                    self.systems_check()

                    # perform planner task instructions
                    if len(tasks) > 0:
                        yield AllOf(self.env, tasks) | listening | self.critical_state

                        if listening.triggered or self.critical_state.triggered:
                            # critical state or new transmission detected. Reconsider plan
                            for task in tasks:
                                if not task.triggered:
                                    if listening.triggered:
                                        task.interrupt("New message received.")
                                    elif self.critical_state.triggered:
                                        task.interrupt("Critical system state detected!")
                                yield task

                            # restart background tasks when needed
                            if listening.triggered:
                                listening = self.env.process(self.listening())

                        # perform manual systems check after all actions have been performed
                        self.systems_check()

                    planner_wait = self.env.process(self.wait_for_plan())
                    self.logger.debug(f'T{self.env.now}:\tDOING PHASE COMPLETE!')

                if listening.triggered:
                    # restart listening process and update plan
                    listening = self.env.process(self.listening())

                if self.critical_state.triggered:
                    self.critical_state = self.env.event()

        except simpy.Interrupt as i:
            self.logger.debug(f'T{self.env.now}: {i.cause} good night!')

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
            elif type(action) == ActuateComponentAction or type(action) == ActuatePowerComponentAction:
                self.actuate_component(action)
            elif type(action) == DeleteMessageAction:
                self.delete_msg(action)
            else:
                raise Exception(f"Maintenance task of type {type(action)} not yet supported.")

            self.planner.completed_action(action, self.state_history.get_latest_state(), self.env.now)
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
            self.turn_off_components(self.component_list)

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
            if component.name == component_actuate.name:
                if type(action) == ActuatePowerComponentAction:
                    power = action.power
                    if power > 0:
                        prev_status = component.status
                        component.turn_on_generator(power)
                        if not prev_status:
                            self.logger.debug(f'T{self.env.now}:\tTurning on {component.name} with power {component.power}W...')
                        else:
                            self.logger.debug(
                                f'T{self.env.now}:\tRegulating {component.name} power to {component.power}W...')
                    else:
                        component.turn_off_generator()
                        self.logger.debug(f'T{self.env.now}:\tTurning off {component.name}...')
                    break
                else:
                    if status:
                        component.turn_on()
                        self.logger.debug(f'T{self.env.now}:\tTurning on {component.name}...')
                    else:
                        component.turn_off()
                        self.logger.debug(f'T{self.env.now}:\tTurning off {component.name}...')
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
            self.logger.debug(f'T{self.env.now}:\tPreparing for measurement...')
            # un package measurement information
            instrument_list = action.instrument_list
            target = action.target

            # check if all components are
            for instrument in instrument_list:
                if not instrument.is_on():
                    raise simpy.Interrupt('Not all required instruments have been activated.')

            # perform measurement
            self.logger.debug(f'T{self.env.now}:\tStarting for measurement...')
            yield self.env.timeout(action.end - action.start)
            self.logger.debug(f'T{self.env.now}:\tCompleted measurement successfully!')

            # process captured data
            # TODO ADD MEASUREMENT RESULTS TO PLANNER KNOWLEDGE BASE:
            #   results = measurementSimulator(target, instrument_list)
            #   planner.update_knowledge_base(measurement_results=results)

            # inform planner of task completion
            self.planner.completed_action(action, self.state_history.get_latest_state(), self.env.now)
            return

        except simpy.Interrupt as i:
            # measurement interrupted
            self.planner.interrupted_action(action, self.state_history.get_latest_state(), self.env.now)
            self.logger.debug(f'T{self.env.now}:\tMeasurement interrupted. {i.cause}')

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

        try:
            if not self.transmitter.is_on():
                raise simpy.Interrupt('Transmitter has not been turned on.')

            msg = action.msg

            msg_timeout = self.env.timeout(msg.timeout)
            send_message = self.env.process(self.transmitter.send_message(self.env, msg, self.logger))

            yield msg_timeout | send_message

            if msg_timeout.triggered and not send_message.triggered:
                self.logger.debug(f'T{self.env.now}:\tMessage transmission timed out.')
                send_message.interrupt("Message transmission timed out.")
                self.planner.interrupted_message(msg, self.env.now)
            elif send_message.triggered:
                self.transmitter.data_rate -= msg.data_rate

                self.planner.completed_action(action, self.state_history.get_latest_state(), self.env.now)
                self.logger.debug(f'T{self.env.now}:\tMessage transmitted successfully!')

                if not msg_timeout:
                    msg_timeout.interrupt("Message transmitted successfully!")

                if self.transmitter.channels.count == 0:
                    self.transmitter.turn_off()
        except simpy.Interrupt as i:
            self.planner.interrupted_action(action, self.state_history.get_latest_state(), self.env.now)
            self.logger.debug(f'T{self.env.now}:\tCancelled Transmission! {i.cause}')
        return

    def charge(self, action: ChargeAction):
        """
        Turns on battery charge status. This will inform update_system() to re-route any excess power being generated
        into the battery so it may be charged at every time-step.
        :param action: Action instruction from the planner indicating start and end time to charging procedure
        :return:
        """
        try:
            self.logger.debug(f'T{self.env.now}:\tStarting battery charging. Initial charge of '
                              f'{self.battery.energy_stored.level/self.battery.energy_capacity*100}%')
            self.battery.turn_on_charge()

            yield self.env.timeout(action.end - action.start)

            self.update_system()
            self.battery.turn_off_charge()

            self.logger.debug(f'T{self.env.now}:\tSuccessfully completed battery charging action! Final charge of '
                              f'{self.battery.energy_stored.level / self.battery.energy_capacity * 100}%')
            return
        except simpy.Interrupt as i:
            self.update_system()
            self.logger.debug(f'T{self.env.now}:\tPaused battery charging! {i.cause} Current charge of '
                              f'{self.battery.energy_stored.level / self.battery.energy_capacity * 100}%')
            self.battery.turn_off_charge()
            self.planner.interrupted_action(action, self.state_history.get_latest_state(), self.env.now)

    '''
    ==========BACKGROUND TASKS==========
    '''
    def wait_for_plan(self):
        """
        Background task that waits for the planner's next instructions
        :return:
        """
        try:
            action = yield self.plan.get()
            self.actions.append(action)

            while len(self.plan.items) > 0:
                action = yield self.plan.get()
                self.actions.append(action)

            self.logger.debug(f'T{self.env.now}:\tReceived instructions from planner!')
        except simpy.Interrupt:
            return

    def listening(self):
        """
        Background tasks that listens for incoming messages. Once a header file is received, it will wait for the rest
        of the message to be received in its incoming buffer so it can pass it to the agent's internal memory. The
        method will wait if there is no memory available in the internal memory. If the wait time goes over a message's
        timeout period it will drop said packet to make room for other incoming packets.
        :return:
        """
        self.logger.debug(f'T{self.env.now}:\tWaiting for any incoming transmission...')
        try:
            if len(self.receiver.received_messages) > 0:
                msg = self.receiver.received_messages.pop()
            else:
                msg = (yield self.receiver.inbox.get())

            msg_timeout = self.env.timeout(msg.timeout)
            msg_reception = self.env.process(self.receiver.receive(self.env, msg, self.on_board_computer, self.logger))

            self.logger.debug(f'T{self.env.now}:\tStarting message reception from A{msg.src.unique_id}!')
            yield msg_timeout | msg_reception

            if msg_timeout.triggered:
                if not msg_reception.triggered:
                    msg_reception.interrupt("Message reception timed out. Dropping packet")
                self.logger.debug(f'T{self.env.now}:\tMessage reception from A{msg.src.unique_id} timed out. '
                                  f'Dropping packet...')
                self.planner.timed_out_message(msg, self.state_history.get_latest_state(), self.env.now)
            elif msg_reception.triggered:
                self.logger.debug(f'T{self.env.now}:\tReceived message from A{msg.src.unique_id}!')
                msg_timeout.interrupt("Message successfully received!")
                msg.reception_time = self.env.now

                # move message from buffer to internal memory
                self.logger.debug(f'T{self.env.now}:\tMoving data from buffer to internal memory!')
                yield self.on_board_computer.data_stored.put(msg.size)
                yield self.receiver.data_stored.get(msg.size)

                # inform planner of message reception
                self.planner.message_received(msg, self.state_history.get_latest_state(), self.env.now)
        except simpy.Interrupt as i:
            self.logger.debug(f'T{self.env.now}:\tMessage reception paused. {i.cause}')

        return

    def systems_check(self):
        # integrate current state at new time
        self.update_system()

        # check if system state is critical
        self.logger.debug(f'T{self.env.now}:\tPerforming system check...')
        critical, cause = self.state_history.get_latest_state().is_critical()

        if critical:
            # if critical, trigger critical state event
            if not self.critical_state.triggered:
                self.logger.debug(f'T{self.env.now}:\tCritical state reached! {cause}')
                self.critical_state.succeed()
        else:
            # state is nominal
            self.logger.debug(f'T{self.env.now}:\tState nominal.')
            if self.critical_state.triggered:
                # if critical state was previously detected, reset event to nominal
                self.critical_state = self.env.event()
        return

    def periodical_systems_check(self):
        """
        Background task that periodically checks the agent's system is in a critical state.
        :return:
        """
        try:
            while True:
                self.systems_check()

                yield self.env.timeout(1)

        except simpy.Interrupt as i:
            self.logger.debug(f'T{self.env.now}:\tPeriodic systems check paused. {i.cause}')
            return

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
                if type(component) == Battery or type(component) == PowerGenerator:
                    power_in += component.power
        power_dif = power_in - power_out

        # calculate time-step
        dt = self.env.now - self.state_history.get_latest_state().t

        # update values
        # -data
        if data_rate_in * dt > 0:
            dD = self.on_board_computer.data_capacity - self.on_board_computer.data_stored.level
            if dD > data_rate_in * dt:
                self.on_board_computer.data_stored.put(data_rate_in * dt)
            else:
                self.on_board_computer.data_stored.put(dD)

        if self.transmitter.data_rate * dt > 0 and self.transmitter.data_stored.level > 0:
            if self.transmitter.data_stored.level >= self.transmitter.data_rate * dt:
                self.transmitter.data_stored.get(self.transmitter.data_rate * dt)
            else:
                self.transmitter.data_stored.get(self.transmitter.data_stored.level)

        # -power
        power_charging = 0
        if self.battery.is_charging() and power_dif >= 0:
            power_charging += power_dif
        if self.battery.is_on():
            power_charging -= self.battery.power

        if power_charging * dt > 0:
            self.battery.energy_stored.put(power_charging * dt)
        elif power_charging * dt < 0:
            self.battery.energy_stored.get(-power_charging * dt)

        # update in state tracking
        self.state_history.update(self, self.component_list, self.env.now)

        # debugging output
        self.logger.debug(f'T{self.env.now}:\tUpdated system status.')
        return

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
    def print_state(self):
        """
        Prints state history to csv file
        :return:
        """
        filename = f'A{self.unique_id}_state.csv'
        file_path = self.results_dir + filename

        with open(file_path, 'w') as f:
            f.write(str(self.state_history))

        f.close()

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
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger

    def plan_to_events(self):
        """
        Converts planner actions to executable events
        :param actions: list of actions to be performed
        :return:
        """
        events = []
        maintenance = []
        for action in self.actions:
            if action.start != self.env.now and not action.is_active(self.env.now):
                self.logger.debug(f'T{self.env.now}:\tAttempting to perform action of type '
                                  f'{type(action)} past its start time t_start={action.start}. '
                                  f'Skipping action.')
                continue

            action.begin()

            action_event = None
            mnt_event = None
            if type(action) == ActuateAgentAction:
                mnt_event = action
            elif type(action) == ActuateComponentAction:
                mnt_event = action
            elif type(action) == ActuatePowerComponentAction:
                mnt_event = action
            elif type(action) == DeleteMessageAction:
                mnt_event = action

            elif type(action) == MeasurementAction:
                action_event = self.env.process(self.measure(action))
            elif type(action) == TransmitAction:
                action_event = self.env.process(self.transmit(action))
            elif type(action) == ChargeAction:
                self.battery.charging = True
                action_event = self.env.process(self.charge(action))

            if action_event is not None:
                events.append(action_event)
            if mnt_event is not None:
                maintenance.append(mnt_event)

        self.actions = []

        return events, maintenance
