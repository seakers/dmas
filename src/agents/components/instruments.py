from src.agents.components.components import Component


class Instrument(Component):
    def __init__(self, env, name, power, data_rate):
        super().__init__(env=env, name=name, power=-power, energy_stored=0, energy_capacity=0,
                         data_rate=data_rate, data_stored=0, data_capacity=0, status=False)
        # self.mass = mass
        # self.volume = volume
        # self.bits_per_pixel = bits_per_pixel
