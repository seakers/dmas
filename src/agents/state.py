from typing import Union

from src.agents.components.components import *


class StateHistory:
    def __init__(self, agent, component_list, t: Union[int, float]):
        self.states = []
        self.update(agent, component_list, t)
        self.parent_agent = agent

    def update(self, agent, component_list, t: Union[int, float]):
        self.states.append(State(agent, component_list, t))

    def get_latest_state(self):
        return self.states[-1]

    def get_state(self, i):
        return self.states[i]


    def __str__(self):
        out = ''
        if len(self.states) > 0:
            out = 't,id,p_in,p_out,p_tot,e_str,e_cap,' \
                  'r_in,r_out,r_tot,d_in,d_in_cap,d_out,d_out_cap,d_mem,d_mem_cap'

            component_list = self.states[0].is_on.keys()
            for component in component_list:
                out += f',{component.name}'

            out += '\n'

            for state in self.states:
                out += str(state)
                for component in component_list:
                    out += f',{int(state.is_on[component] == True)}'
                out += '\n'
        return out


class State:
    def __init__(self, agent, component_list, t: Union[int, float]):
        self.parent_agent = agent

        data_rate_in = 0
        power_out = 0
        power_in = 0
        power_tot = 0
        self.is_on = dict.fromkeys(component_list, False)

        for component in component_list:
            self.is_on[component] = component.status

            if (component.is_on()
                    and type(component) != Transmitter):
                data_rate_in += component.data_rate
            if component.is_on():
                if component.power > 0:
                    power_in += component.power
                else:
                    power_out -= component.power
                power_tot += component.power

        self.dod = agent.battery.dod
        self.charging = agent.battery.is_charging()
        self.buffer_in_capacity = agent.receiver.data_capacity
        self.buffer_out_capacity = agent.transmitter.data_capacity

        self.data_rate_in = data_rate_in
        self.data_rate_out = agent.transmitter.data_rate
        self.data_rate_tot = data_rate_in - agent.transmitter.data_rate

        self.data_buffer_in = agent.receiver.data_stored.level
        self.data_memory = agent.on_board_computer.data_stored.level
        self.data_buffer_out = agent.transmitter.data_stored.level
        self.data_capacity = agent.on_board_computer.data_capacity

        self.power_in = power_in
        self.power_out = power_out
        self.power_tot = power_tot
        self.energy_capacity = agent.battery.energy_capacity

        self.energy_stored = agent.battery.energy_stored.level

        self.t = t

        self.critical = False

    def __str__(self):
        """
        Prints state in the following format:
        t,id,p_in,p_out,p_tot,e_str,e_cap,r_in,r_out,r_tot,d_in,d_in_cap,d_out,d_out_cap,d_mem,d_mem_cap
        """
        return f'{self.t},{self.parent_agent.unique_id},{self.power_in},{self.power_out},{self.power_tot},' \
               f'{self.energy_stored},{self.energy_capacity},' \
               f'{self.data_rate_in},{self.data_rate_out},{self.data_rate_tot},' \
               f'{self.data_buffer_in},{self.buffer_in_capacity},{self.data_buffer_out},{self.buffer_out_capacity}' \
               f',{self.data_memory},{self.data_capacity}'

    def is_critical(self):
        """
        Checks if it is a critical state. Checks for batteries being below their maximum depth-of-discharge
        or being overcharged, checks to see if power is being properly supplied to other components, and checks if there
        is a memory overflow in the internal memory.
        :return:
        """
        critical = False
        cause = ''

        if (1 - self.energy_stored / self.energy_capacity) >= self.dod:
            cause = 'Battery has reached its maximum depth-of-discharge level'
            critical = True
        elif self.energy_stored == self.energy_capacity and self.charging:
            cause = 'Battery is full and is still charging.'
            critical = True
        elif self.power_tot < 0:
            cause = f'Insufficient power being generated (P_in={self.power_in}, P_out={self.power_out})'
            critical = True
        elif self.power_tot > 0 and not self.charging:
            cause = f'Excess power being generated and is not being used for charging (P_in={self.power_in}, P_out={self.power_out})'
            critical = True
        elif self.data_memory == self.data_capacity and self.data_rate_in > 0:
            cause = f'Pn-board memory full and data is coming in faster than it is leaving.'
            critical = True

        return critical, cause