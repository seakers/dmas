class State:
    def __init__(self, agent, component_list):
        self.agent = agent
        self.status = True
        self.health = True

        self.power_generation = 0
        self.energy_stored = 0
        self.energy_capacity = 0

        self.data_rate = 0
        self.data_stored = 0
        self.data_capacity = 0

        for component in component_list:
            # power
            self.power_generation += component.power_generation
            self.energy_stored += component.energy_stored
            self.energy_capacity += component.energy_capacity

            # data memory
            self.data_rate += component.data_rate
            self.data_stored += component.data_stored
            self.data_capacity += component.data_capacity

    def update(self, component_list):
        self.power_generation = 0
        self.energy_stored = 0

        self.data_rate = 0
        self.data_stored = 0
        for component in component_list:
            # power
            self.power_generation += component.power_generation
            self.energy_stored += component.energy_stored

            # data memory
            self.data_rate += component.data_rate
            self.data_stored += component.data_stored
