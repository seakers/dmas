
class AgentState():
    def __init__(self, agent, dt=1):
        self.dt = dt
        self.update(agent=agent)

    def update(self, agent):
        self.power_in = 0
        self.power_out = 0
        self.power_stored = 0
        self.power_capacity = 0
        self.data_in = 0
        self.data_out = 0
        self.data_stored = 0
        self.data_capacity = 0

        for component in agent.component_list:
            power_generation, power_usage, power_stored, power_capacity = component.get_power_info()
            data_generation, data_usage, data_stored, data_capacity = component.get_data_info()

            if component.is_on():
                self.power_in += power_generation
                self.power_out += power_usage

                self.data_in += data_generation
                self.data_out += data_usage

            self.power_stored += power_stored
            self.power_capacity += power_capacity
            self.data_stored += data_stored
            self.data_capacity += data_capacity

        for incoming_message in agent.get_incoming_mssages():
            self.data_in += incoming_message.get_data_rate()

        for outgoing_message in agent.get_outgoing_mssages():
            self.data_out += outgoing_message.get_data_rate()

    def is_power_failure_state(self):
        return self.power_in < self.power_out
