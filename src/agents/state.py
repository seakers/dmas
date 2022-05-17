from typing import Union

from src.agents.agent import AbstractAgent
from src.agents.components.components import *


class State:
    def __init__(self, agent: AbstractAgent, component_list, t: Union[int,float]):
        self.data_rate_in = []
        self.data_rate_out = []
        self.data_rate_total = []

        self.data_buffer_in = []
        self.data_memory = []
        self.data_buffer_out = []
        self.data_capacity = agent.on_board_computer.data_capacity

        self.power_in = []
        self.power_out = []
        self.power_tot = []

        self.energy_stored = []
        self.energy_capacity = agent.battery.data_capacity

        self.t = []
        self.t.append(t)

        self.isOn = dict.fromkeys(component_list,[])

        self.update(agent, component_list, t)

    def update(self, agent: AbstractAgent, component_list, t: Union[int, float]):
        data_rate_in = 0
        power_out = 0
        power_in = 0
        power_tot = 0
        for component in component_list:
            self.isOn[component].append(component.is_on())

            if (component.is_on()
                    and type(component) != Transmitter
                    and type(component) != Receiver):
                data_rate_in += component.data_rate
            if component.is_on():
                if component.power > 0:
                    power_in += component.power
                else:
                    power_out -= component.power
                power_tot += component.power

        self.data_rate_in.append(data_rate_in)
        self.data_rate_out.append(agent.transmitter.data_rate)

        self.data_buffer_in.append(agent.receiver.data_stored.level)
        self.data_memory.append(agent.on_board_computer.data_stored.level)
        self.data_buffer_out.append(agent.transmitter.data_stored.level)

        self.power_in.append(power_in)
        self.power_out.append(power_out)
        self.power_tot.append(power_tot)

        self.energy_stored.append(agent.battery.energy_stored)

        self.t.append(t)