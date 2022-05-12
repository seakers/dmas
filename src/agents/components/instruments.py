from src.agents.components.components import Component


class Instrument(Component):
    def __init__(self, power, data_rate):
        super().__init__(power_generation=-power, energy_stored=0, energy_capacity=0,
                         data_rate=data_rate, data_stored=0, data_capacity=0, status=False)
