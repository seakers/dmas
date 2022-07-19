from dmas.agents.components.components import Component


class Instrument(Component):
    def __init__(self, env, name, modes, power, data_rate):
        super().__init__(env=env, name=name, power=-power, energy_stored=0, energy_capacity=0,
                         data_rate=data_rate, data_stored=0, data_capacity=0, status=False)
        # self.mass = mass
        # self.volume = volume
        # self.bits_per_pixel = bits_per_pixel
        self.modes = modes

    def from_dict(d, env):
        name = d.get('name', None)
        
        mode_dict = d.get("mode", None)
        if(mode_dict): # multiple modes may exist
            if isinstance(mode_dict, list):
                modes = [x.get("pointingOption") for x in mode_dict]
            else:
                modes = [mode_dict.get("pointingOption")]
        else:
            modes = [{"referenceFrame": "NADIR_POINTING", "convention": "SIDE_LOOK", "sideLookAngle":0}]

        return Instrument(env, name, modes, 0, 0)