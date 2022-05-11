from mesa import Agent

from src.agents.AgentState import AgentState
from src.agents.components.Battery import Battery
from src.agents.components.Comms import Comms
from src.agents.planners.Action import TransmitAction, ActuateAction, AgentActuateAction, DataUpdateAction, \
    DropMessageAction, BatteryRechargeAction


class SimulationAgent(Agent):
    def __init__(self, unique_id, planner, model, start_epoc=0, time_step=1, component_list=None):
        """
        Constructor
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

        self.planner = planner
        self.state = AgentState(self)

    def step(self) -> None:
        # Update epoc
        self.epoc += self.dt

        # If agent is not active, do nothing
        if not self.alive:
            return

        # Update State
        self.read_incoming_messages()
        self.state.update(self)

        # print(self.state)

    def advance(self) -> None:
        # If agent is not active, do nothing
        if not self.alive:
            return

        # Give state to planner and actions
        self.planner.update_planner(self, self.state, self.epoc)
        plan = self.planner.get_plan()

        while len(plan) > 0 and self.alive:
            # Perform action
            action = plan.pop()
            if type(action) == TransmitAction:
                self.transmit(action)
            elif type(action) == ActuateAction:
                self.actuate(action)
            elif type(action) == AgentActuateAction:
                self.agent_actuate(action)
            elif type(action) == DropMessageAction:
                self.message_drop(action)
            elif type(action) == DataUpdateAction:
                self.update_data(action)
            elif type(action) == BatteryRechargeAction:
                self.recharge_battery(action)
            else:
                raise Exception("Action of type " + type(action) + " not yet supported")

        # Check if in failure state
        self.state.update(self)
        if self.state.is_power_failure_state():
            self.alive = False

        # It in nominal state, move to next time-step
        return

    def get_incoming_messages(self):
        return self.incoming_messages

    def get_outgoing_messages(self):
        return self.outgoing_messages

    def read_incoming_messages(self):
        # Check if EOF messages have been received that close the transmission of a message
        for message in self.incoming_messages:
            if message.bits == 0:
                print("Agent " + str(self.unique_id) + ": received a new message transmission from Agent "
                      + str(message.get_receiver_id()) + "!")

            # update message transmission status
            message.update_transmission_step()
            print("Agent " + str(self.unique_id) + ": message reception status from Agent "
                  + str(message.get_receiver_id()) + " (" + str(message.bits) + "/" + str(message.size) + ")")

            # if transmission is complete, remove from incoming messages and send to received messages
            if message.is_eof():
                print("Agent " + str(self.unique_id) + ": message reception from Agent "
                      + str(message.get_receiver_id()) + " complete!")
                message.set_receipt_epoc(self.epoc)
                self.received_messages.append(message)
                self.incoming_messages.remove(message)

    def transmit(self, action):
        # TODO ONLY ALLOW TRANSMISSION WHEN IN FIELD OF VIEW OF TARGET
        message = action.get_message()

        if not self.outgoing_messages.__contains__(message):
            comms = self.get_comms(selection='nt')
            if len(comms) == 0:
                # No available comms subsystem available for transmission at this time. Will skip this action
                return
            else:
                free_comms = comms[0]
                actuate_comms = ActuateAction(free_comms.get_name(), self.epoc)
                self.actuate(actuate_comms)

                free_comms.add_data(data=message.size)

                print("Agent " + str(self.unique_id) + ": starting transmission towards Agent "
                      + str(message.get_receiver_id()) + "...")
                self.send_message(message)
                self.outgoing_messages.append(message)
                print("Agent " + str(self.unique_id) + ": message transmission status from Agent "
                      + str(message.get_receiver_id()) + " (" + str(message.bits) + "/" + str(message.size) + ")")
                return

        message.update_transmission_step()
        print("Agent " + str(self.unique_id) + ": message transmission status from Agent "
              + str(message.get_receiver_id()) + " (" + str(message.bits) + "/" + str(message.size) + ")")
        if message.is_eof():
            print("Agent " + str(self.unique_id) + ": transmission towards Agent "
                  + str(message.get_receiver_id()) + " complete!")
            self.outgoing_messages.remove(message)

            comms = self.get_comms(selection='t')
            free_comms = comms[0]
            actuate_comms = ActuateAction(free_comms.get_name(), self.epoc, status=False)
            self.actuate(actuate_comms)
        return

    def actuate(self, action):
        for component in self.component_list:
            if component.get_name() == action.get_component_name():
                if action.get_actuation_status():
                    print("Agent " + str(self.unique_id) + ": turning on component " + component.get_name())
                    component.turn_on()
                else:
                    print("Agent " + str(self.unique_id) + ": turning off component " + component.get_name())
                    component.turn_off()
                break

    def agent_actuate(self, action):
        self.alive = action.get_actuation_status()
        return

    def message_drop(self, action):
        # Dropping latest incoming message to make room for incoming data
        print("Agent " + str(self.unique_id) + ": dropping last incoming message")

        message_to_delete = action.get_message()

        deleted_message = None
        for message in self.incoming_messages:
            if message.__cmp__(message_to_delete):
                deleted_message = message

        self.incoming_messages.remove(deleted_message)

        data_storage_all = self.get_comms()
        data_to_delete = deleted_message.bits + deleted_message.get_data_rate() * self.dt

        for comms in data_storage_all:
            if comms.data_stored - data_to_delete >= 0:
                comms.add_data(-data_to_delete)
                break
            else:
                comms.empty_data_storage()
                data_to_delete -= comms.data_capacity

        return

    def update_data(self, action):
        data_rate = action.get_data()

        all_coms = self.get_comms()
        for storage in all_coms:
            storage.update_data_storage(data_rate=data_rate / len(all_coms))

        commStorage = 0
        commCapacity = 0
        for component in self.component_list:
            if type(component) == Comms:
                data_info = component.get_data_info()
                commStorage += data_info[2]
                commCapacity += data_info[3]

        print("Agent " + str(self.unique_id) + ": memory storage status " + str(commStorage) + "/" + str(commCapacity))

        return

    def recharge_battery(self, action):
        battery_name = action.get_battery_name()
        power_in = action.get_power_in()

        all_batteries = self.get_batteries()
        for battery in all_batteries:
            if battery.get_name() == battery_name:
                battery.update_energy_storage(power_in=power_in)

        powerStorage = 0
        powerCapacity = 0
        for component in self.component_list:
            if type(component) == Battery:
                data_info = component.get_power_info()
                powerStorage += data_info[2]
                powerCapacity += data_info[3]

        print("Agent " + str(self.unique_id) + ": power storage status " + str(powerStorage) + "/" + str(powerCapacity))

        return

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
                if selection == 'all':
                    batteries.append(component)
                elif selection == 'nf':
                    if not component.is_full():
                        batteries.append(component)
                elif selection == 'f':
                    if component.is_full():
                        batteries.append(component)
                else:
                    raise Exception("Selection of type " + selection + " not supported.")

        return batteries