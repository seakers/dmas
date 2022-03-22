from mesa import Agent
from src.agents.components.Battery import Battery
from src.agents.components.Comms import Comms
from src.agents.components.Instrument import Instrument


class AbstractAgent(Agent):
    """
    Abstract Class representing an agent in the simulation. Must be implemented as a satellite or a ground station
    """

    def __init__(self, unique_id, component_list=None, planner=None, model=None):
        """
        Constructor for and Abstract Agent
        :param unique_id: id integer used to identify this agent
        :param component_list: list of components contained in the agent
        :param planner: planner being used for this agent
        :param model: multi agent model being used in the simulation
        """
        super().__init__(unique_id=unique_id, model=model)

        self.alive = True

        self.message_counter = 0
        self.incoming_messages = []
        self.received_messages = []
        self.outgoing_messages = []

        self.component_list = []
        if component_list is not None:
            for component in component_list:
                self.component_list.append(component.copy())

        self.plan = []
        self.planner = planner.copy()

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

        # Read Incoming Messages
        self.read_incoming_messages()

        # Update State
        self.update_power_state()
        self.update_data_state()
        self.update_attitude_state()

        # Create Plan
        self.plan = []
        self.plan = self.planner.update_plan(self.component_list, self.received_messages)
        pass

    def advance(self) -> None:
        """
        Agent performs actions on self and the environment
        Actions allowed:
        -Turn components on and off
        -Transmit messages to other agents
        -Perform Measurements
        -Perform Maneuver
        """
        if not self.alive:
            pass

        pass

    def update_power_state(self):
        """
        Updates energy levels in the agent's batteries based on active subsystems and active power generators
        :return: None
        """
        # If agent is not active, do nothing
        if not self.alive:
            pass

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
        else:
            # Power generation may exceed consumption. Recharge Batteries if possible
            battery_list = self.get_batteries(empty=True)
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
            pass

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
        data_storage = self.get_comms(empty=True)
        n_storage = len(data_storage)

        if n_storage < 1 and data_rate > 0.0:
            # Not enough storage available for incoming data.

            if len(self.incoming_messages) > 0:
                # Dropping latest incoming message to make room for incoming data
                data_storage_all = self.get_comms()
                top_message = self.incoming_messages.pop()
                data_to_delete = top_message.bits

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
            for storage in data_storage:
                storage.update_data_storage(data_rate=data_rate)

        return

    def update_attitude_state(self) -> None:
        """
        Abstract functio nthat updates current agent's attitude based on the agent's active actuators.
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
            if type(component) is type (Instrument):
                if active and component.is_on():
                    instruments.append(component)
                elif not active:
                    instruments.append(component)

        return instruments

    def get_comms(self, empty=False) -> list:
        """
        Returns list of communication subsystems contained in the agent's component list
        :param empty: boolean toggle that, if true, only returns batteries that are not to their full capacity
        :return: list of communication subsystems contained in the agent
        """
        comms = []
        for component in self.component_list:
            if type(component) is type(Comms):
                if empty and not component.is_full():
                    comms.append(component)
                elif not empty:
                    comms.append(component)

        return comms

    def get_batteries(self, empty=False) -> list:
        """
        Returns list of battery components contained in the agent's component list
        :param empty: boolean toggle that, if true, only returns batteries that are not to their full capacity
        :return: list of batteries contained in the agent
        """
        batteries = []
        for component in self.component_list:
            if type(component) is type(Battery):
                if empty and not component.is_full():
                    batteries.append(component)
                elif not empty:
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
        other_agent.incoming_messages.append(message)

    def read_incoming_messages(self):
        # Check if EOF messages have been received that close the transmission of a message
        for message in self.incoming_messages:
            message.update_transmission_step()
            if message.is_eof():
                self.received_messages.append(message)
                self.incoming_messages.remove(message)
