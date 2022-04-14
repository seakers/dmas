from src.agents.AgentState import AgentState
from src.agents.planners.Action import TransmitAction, ActuateAction, AgentActuateAction


class SimulationAgent:
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
        self.state.update(self)

    def advance(self) -> None:
        # If agent is not active, do nothing
        if not self.alive:
            return

        # Give state to planner and actions
        action = self.planner.update_plan(self, self.state)
        while action is not None and self.alive:
            if type(action) == TransmitAction:
                self.transmit(action)
            elif type(action) == ActuateAction:
                self.actuate(action)
            elif type(action) == AgentActuateAction:
                self.agent_actuate(action)
            else:
                raise Exception("Action of type " + type(action) + " not yet supported")

            action = self.planner.update_plan(self, self.state)

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

    def transmit(self, action):
        # TODO ONLY ALLOW TRANSMISSION WHEN IN FIELD OF VIEW OF TARGET

        message = action.get_message()
        if not self.outgoing_messages.__contains__(message):
            comms = self.get_comms(selection='nt')
            if len(comms) == 0:
                # No available comms subsystem available for transmission at this time. Will skip this action
                return
            else:
                print("Agent " + str(self.unique_id) + ": starting transmission...")
                self.send_message(message)
                self.outgoing_messages.append(message)
                print("Agent " + str(self.unique_id) + ": transmission status " + str(message.bits) + "/" + str(
                    message.size))
                return

        message.update_transmission_step()
        print("Agent " + str(self.unique_id) + ": transmission status " + str(message.bits) + "/" + str(
            message.size))
        if message.is_eof():
            print("Agent " + str(self.unique_id) + ": transmission complete!")
            self.outgoing_messages.remove(message)
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

