class State:
    def __init__(self, agent, component_list, t):
        self.agent = agent
        self.status = True
        self.health = True

        # Initialize state arrays
        self.t = []

        self.power_deficit = []
        self.power_in = []
        self.power_out = []
        self.energy_stored = []
        self.energy_capacity = 0

        self.data_rate = []
        self.data_stored = []
        self.data_capacity = 0

        # Check for initial state
        for component in component_list:
            # power
            self.energy_capacity += component.energy_capacity

            # data memory
            self.data_capacity += component.data_capacity

        self.update(component_list, t)

    def update(self, component_list, t):
        power_deficit = 0
        power_in = 0
        power_out = 0
        energy_stored = 0

        data_rate = 0
        data_stored = 0
        for component in component_list:
            # power
            power_deficit += component.power_generation
            if component.power_generation > 0:
                power_in += component.power_generation
            else:
                power_out -= component.power_generation

            energy_stored += component.energy_stored

            # data memory
            data_rate += component.data_rate
            data_stored += component.data_stored

        # Save to state arrays
        self.t.append(t)

        self.power_deficit.append(power_deficit)
        self.power_in.append(power_in)
        self.power_out.append(power_out)
        self.energy_stored.append(energy_stored)

        self.data_rate.append(data_rate)
        self.data_stored.append(data_stored)

    def get_last_state(self):
        i = len(self.t) - 1

        t = self.t[i]
        power_deficit = self.power_deficit[i]
        power_in = self.power_in[i]
        power_out = self.power_out[i]
        energy_stored = self.energy_stored[i]
        energy_capacity = self.energy_capacity

        data_rate = self.data_rate[i]
        data_stored = self.data_stored[i]
        data_capacity = self.data_capacity

        return t, power_deficit, power_in, power_out, energy_stored, \
               energy_capacity, data_rate, data_stored, data_capacity

