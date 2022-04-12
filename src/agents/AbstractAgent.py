from mesa import Agent
from src.agents.components.Battery import Battery
from src.agents.components.Comms import Comms
from src.agents.components.Instrument import Instrument
from src.agents.planners.Action import TransmitAction, ActuateAction
from src.messages import Message
from src.messages.Message import AbstractMessage


class AbstractAgent(Agent):
    """
    Abstract Class representing an agent in the simulation. Must be implemented as a satellite or a ground station
    """

    def __init__(self, unique_id, planner, model, start_epoc=0, time_step=1, component_list=None):
        """
        Constructor for and Abstract Agent
        :param unique_id: id integer used to identify this agent
        :param planner: planner being used for this agent
        :param model: multi agent model being used in the simulation
        :param start_epoc: starting epoc in [s]
        :param time_step: simulation time-step in [s]
        :param component_list: list of components contained in the agent
        """
        super().__init__(unique_id=unique_id, model=model)

        self.alive = True

        self.epoc = start_epoc
        self.dt = time_step

        self.message_counter = 0
        self.incoming_messages = []
        self.received_messages = []
        self.outgoing_messages = []

        self.component_list = []
        if component_list is not None:
            for component in component_list:
                self.component_list.append(component)

        self.plan = []
        self.planner = planner

        eps = 1.0
        while eps + 1 > 1:
            eps /= 2
        eps *= 2
        self.epsilon = eps

    def step(self) -> None:
        """
        Agent processes received information from other agents, updates state, and thinks what to do.
        Actions allowed:
        -Reads incoming messages
        -Updates power, data, and attitude states
        -Sends updated information to planner, which returns next action to be performed
        """

        # If agent is not active, do nothing
        if not self.alive:
            pass

        # Update State
        self.update_power_state()
        self.update_data_state()
        self.update_attitude_state()

        # Read Incoming Messages
        self.read_incoming_messages()

        if self.epoc == 4:
            x = 1

        # Update Plan
        self.planner.update_plan(self.component_list, self.received_messages, self.epoc)
        self.plan = self.planner.get_plan()
        return

    def advance(self) -> None:
        """
        Agent performs actions on self and the environment. Abstract function and must be implemented.

        Actions allowed:
        -Turn components on and off
        -Transmit messages to other agents
        -Delete received message from memory
        -Perform Measurements
        -Perform Maneuver
        """
        # If agent is not active, do nothing
        if not self.alive:
            pass

        # Perform actions in plan
        for action in self.plan:
            if type(action) == TransmitAction:
                message = action.get_message()
                if not self.outgoing_messages.__contains__(message):
                    comms = self.get_comms(selection='nt')
                    if len(comms) == 0:
                        # No available comms subsystem available for transmission at this time. Will skip this action
                        continue
                    else:
                        print("Agent " + str(self.unique_id) + ": starting transmission...")
                        # Activates transmission for the first available comms subsystem
                        comms_component = comms[0]
                        print("Agent " + str(self.unique_id) + ": turning on component " + comms_component.get_name())
                        comms_component.turn_on()
                        comms_component.add_data(message.size)

                        self.send_message(message)
                        self.outgoing_messages.append(message)
                        print("Agent " + str(self.unique_id) + ": transmission status " + str(message.bits) + "/" + str(
                            message.size))
                        continue

                message.update_transmission_step()
                print("Agent " + str(self.unique_id) + ": transmission status " + str(message.bits) + "/" + str(message.size))
                if message.is_eof():
                    print("Agent " + str(self.unique_id) + ": transmission complete!")
                    self.outgoing_messages.remove(message)
                    if len(self.outgoing_messages) == 0:
                        for comms in self.get_comms():
                            i = self.component_list.index(comms)
                            print("Agent " + str(self.unique_id) + ": turning off component " + comms.get_name())
                            self.component_list[i].turn_off()
            elif type(action) == ActuateAction:
                for component in self.component_list:
                    if component.get_name() == action.get_component_name():
                        if action.get_actuation_status():
                            print("Agent " + str(self.unique_id) + ": turning on component " + component.get_name())
                            component.turn_on()
                        else:
                            print("Agent " + str(self.unique_id) + ": turning off component " + component.get_name())
                            component.turn_off()
            else:
                raise Exception("Acction of type " + type(action) + " not yet supported")

        # Update internal clock
        self.epoc += self.dt

        return

    def update_power_state(self):
        """
        Updates energy levels in the agent's batteries based on active subsystems and active power generators
        :return: None
        """
        # If agent is not active, do nothing
        if not self.alive:
            return

        battery_list = self.get_batteries()
        for battery in battery_list:
            battery.update_energy_storage()

        # Check all components and track their power consumption and generation
        power_in = 0
        power_out = 0
        for component in self.component_list:
            if component.is_on():
                info = component.get_power_info()
                power_generation = info[0]
                power_usage = info[1]

                power_in += power_generation
                power_out += power_usage

        power_total = power_in - power_out

        if power_in < power_out:
            # Power consumption exceeds generation. Turning off agent.
            self.alive = False
            print("Agent ID %i offline. Power consumption exceeded power generation capabilities" % self.unique_id)
        elif power_in >= power_out and power_in > 0:
            # Power generation may exceed consumption. Recharge Batteries if possible
            battery_list = self.get_batteries(selection='nf')
            n_batteries = len(battery_list)

            if n_batteries < 1 and power_in > power_out:
                # No batteries in the agent able to store extra power coming in.Turning off agent
                self.alive = False
                print("Agent ID %i offline. Power generation exceeded power storage capabilities" % self.unique_id)

            for battery in battery_list:
                battery.update_energy_storage(power_in=power_total/n_batteries)
        return

    def update_data_state(self) -> None:
        """
        Updates data contained in its memory by checking incoming and outgoing messages along with active instruments
        :return: None
        """
        # If agent is not active, do nothing
        if not self.alive:
            return

        # Check all components and track their data generation
        data_in = 0
        data_out = 0
        for component in self.component_list:
            if component.is_on():
                info = component.get_data_info()
                data_generation = info[0]
                data_in += data_generation

        # Check all incoming and outgoing messages and their data rates
        for incoming_message in self.incoming_messages:
            data_in += incoming_message.get_data_rate()

        for outgoing_message in self.outgoing_messages:
            data_out += outgoing_message.get_data_rate()

        data_rate = data_in - data_out

        # Check for data storage with room for incoming data
        data_storage = self.get_comms(selection='nf')
        n_storage = len(data_storage)

        if n_storage < 1 and data_rate > 0.0:
            # Not enough storage available for incoming data.
            print("Agent " + str(self.unique_id) + ": memory full.")

            if len(self.incoming_messages) > 0:
                # Dropping latest incoming message to make room for incoming data
                print("Agent " + str(self.unique_id) + ": dropping last incoming message")

                data_storage_all = self.get_comms()
                top_message = self.incoming_messages.pop()
                data_to_delete = top_message.bits + top_message.get_data_rate() * self.dt

                for comms in data_storage_all:
                    if comms.data_storage - data_to_delete >= 0:
                        comms.add_data(-data_to_delete)
                        break
                    else:
                        comms.empty_data_storage()
                        data_to_delete -= comms.data_capacity
            else:
                # No incoming messages available to be dropped. Deactivating instrument.
                instruments = self.get_instruments(active=True)
                if len(instruments) > 0:
                    instruments[0].turn_off()
        else:
            # data storage might still have room to receive incoming data
            all_coms = self.get_comms(selection='all')
            for storage in all_coms:
                storage.update_data_storage(data_rate=data_rate/len(all_coms))

            commStorage = 0
            commCapacity = 0
            for component in self.component_list:
                if type(component) == Comms:
                    data_info = component.get_data_info()
                    commStorage += data_info[2]
                    commCapacity += data_info[3]

            print("Agent " + str(self.unique_id) + ": memory status " + str(commStorage) + "/" + str(commCapacity))

            if commStorage > commCapacity:
                print("Agent " + str(self.unique_id) + ": memory full.")

                if len(self.incoming_messages) > 0:
                    # Dropping latest incoming message to make room for incoming data
                    print("Agent " + str(self.unique_id) + ": dropping last incoming message")

                    data_storage_all = self.get_comms()
                    top_message = self.incoming_messages.pop()
                    data_to_delete = top_message.bits + top_message.get_data_rate() * self.dt

                    for comms in data_storage_all:
                        if comms.data_storage - data_to_delete >= 0:
                            comms.add_data(-data_to_delete)
                            break
                        else:
                            comms.empty_data_storage()
                            data_to_delete -= comms.data_capacity
                else:
                    # No incoming messages available to be dropped. Deactivating instrument.
                    instruments = self.get_instruments(active=True)
                    if len(instruments) > 0:
                        instruments[0].turn_off()

                commStorage = 0
                commCapacity = 0
                for component in self.component_list:
                    if type(component) == Comms:
                        data_info = component.get_data_info()
                        commStorage += data_info[2]
                        commCapacity += data_info[3]

                print("Agent " + str(self.unique_id) + ": memory status " + str(commStorage) + "/" + str(commCapacity))
        return

    def update_attitude_state(self) -> None:
        """
        Abstract function that updates current agent's attitude based on the agent's active actuators.
        Must be implemented by each specific implementation of the AbstractAgent class
        :return: None
        """
        pass

    def get_instruments(self, active=False) -> list:
        """
        Returns the list of instruments contained in this agent's component list
        :param active: boolean toggle that, if true, only returns instruments that are active
        :return: list of instruments contained in agent
        """
        instruments = []
        for component in self.component_list:
            if type(component) is Instrument:
                if active and component.is_on():
                    instruments.append(component)
                elif not active:
                    instruments.append(component)

        return instruments

    def get_comms(self, selection='all') -> list:
        """
        Returns list of communication subsystems contained in the agent's component list
        :param selection: indicates the selection of comms systems based on their availability or status
        :return: list of communication subsystems contained in the agent
        """
        comms = []
        for component in self.component_list:
            if type(component) is Comms:
                if selection == 'all':
                    comms.append(component)
                elif selection == 'nt':
                    # not transmitting
                    if not component.is_on():
                        comms.append(component)
                elif selection == 't':
                    # currently transmitting
                    if component.is_on():
                        comms.append(component)
                elif selection == 'nf':
                    # not full
                    if not component.is_full():
                        comms.append(component)
                elif selection == 'f':
                    # is full
                    if component.is_full():
                        comms.append(component)
                else:
                    raise Exception("Selection of type " + selection + " not supported.")

        return comms

    def get_batteries(self, selection='all') -> list:
        """
        Returns list of battery components contained in the agent's component list
        :param empty: boolean toggle that, if true, only returns batteries that are not to their full capacity
        :return: list of batteries contained in the agent
        """
        batteries = []
        for component in self.component_list:
            if type(component) is Battery:
                # if empty and not component.is_full():
                #     batteries.append(component)
                # elif not empty:
                #     batteries.append(component)
                if selection == 'all':
                    batteries.append(component)
                elif selection == 'nf':
                    if not component.is_full():
                        batteries.append(component)
                elif selection == 'f':
                    if component.is_full():
                        batteries.append(component)

        return batteries

    def send_message(self, message) -> None:
        """
        Sends a message to another agent with a given id
        TODO: Add checks that only allow a message to be sent only if the agents are accessing each other
        :param message: message to be transmitted
        :return:
        """
        unique_id = message.get_receiver_id()
        other_agent = self.model.schedule.agents[unique_id]
        other_agent.incoming_messages.append(message.copy())

    def read_incoming_messages(self):
        # Check if EOF messages have been received that close the transmission of a message
        for message in self.incoming_messages:
            if message.bits == 0:
                print("Agent " + str(self.unique_id) + ": received a new transmission!")

            # update message transmission status
            message.update_transmission_step()
            print("Agent " + str(self.unique_id) + ": transmission reception status " + str(message.bits) + "/" + str(message.size))

            # if transmission is complete, remove from incoming messages and send to received messages
            if message.is_eof():
                print("Agent " + str(self.unique_id) + ": transmission complete!")
                message.set_receipt_epoc(self.epoc)
                self.received_messages.append(message)
                self.incoming_messages.remove(message)
