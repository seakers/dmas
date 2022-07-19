from typing import Union

from dmas.agents.components.components import *
from dmas.agents.models.platform import Platform


class StateHistory:
    def __init__(self, agent, platform: Platform, t: Union[int, float]):
        self.states = []
        self.parent_agent = agent
        self.update(platform, t)
        self.t_critical = -1

    def update(self, platform: Platform, t: Union[int, float]):
        state = State(self.parent_agent, platform, t)

        for prev_state in self.states:
            if prev_state == state:
                return

        self.states.append(state)

    def get_latest_state(self):
        return self.get_state(-1)

    def get_state(self, i):
        return self.states[i]

    def __str__(self):
        out = ''
        if len(self.states) > 0:
            out = 't,id,' \
                  'rx,ry,rz,' \
                  'vx,vy,vz,eclipse,' \
                  'p_in,p_out,p_tot,e_str,e_cap,' \
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
    def __init__(self, agent, platform: Platform, t: Union[int, float]):
        self.parent_agent = agent

        component_list = platform.component_list

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

        self.dod = platform.battery.dod
        self.charging = platform.battery.is_charging()
        self.buffer_in_capacity = platform.receiver.data_capacity
        self.buffer_out_capacity = platform.transmitter.data_capacity

        self.data_rate_in = data_rate_in
        self.data_rate_out = platform.transmitter.data_rate
        self.data_rate_tot = data_rate_in - platform.transmitter.data_rate

        self.data_buffer_in = platform.receiver.data_stored.level
        self.data_memory = platform.on_board_computer.data_stored.level
        self.data_buffer_out = platform.transmitter.data_stored.level
        self.data_capacity = platform.on_board_computer.data_capacity

        self.power_in = power_in
        self.power_out = power_out
        self.power_tot = power_tot
        self.energy_capacity = platform.battery.energy_capacity

        self.energy_stored = platform.battery.energy_stored.level

        self.t = t

        self.pos = [-1, -1, -1]
        self.vel = [-1, -1, -1]
        for i in range(3):
            self.pos[i] = platform.pos[i]
            self.vel[i] = platform.vel[i]
        self.eclipse = platform.eclipse

        self.critical = False

    def __eq__(self, other):
        same_agent = self.parent_agent == other.parent_agent
        same_component_status = True

        for component in self.is_on.keys():
            if self.is_on[component] != other.is_on[component]:
                same_component_status = False
                break

        same_dod = self.dod == other.dod
        same_charging_status = self.charging == other.charging
        same_buffer_in_capacity = self.buffer_in_capacity == other.buffer_in_capacity
        same_buffer_out_capacity = self.buffer_out_capacity == other.buffer_out_capacity

        same_data_rate_in = self.data_rate_in == other.data_rate_in
        same_data_rate_out = self.data_rate_out == other.data_rate_out
        same_data_rate_tot = self.data_rate_tot == other.data_rate_tot

        same_data_buffer_in = self.data_buffer_in == other.data_buffer_in
        same_data_memory = self.data_memory == other.data_memory
        same_data_buffer_out = self.data_buffer_out == other.data_buffer_out
        same_data_capacity = self.data_capacity == other.data_capacity

        same_power_in = self.power_in == other.power_in
        same_power_out = self.power_out == other.power_out
        same_power_tot = self.power_tot == other.power_tot
        same_energy_capacity = self.energy_capacity == other.energy_capacity
        same_energy_stored = self.energy_stored == other.energy_stored

        same_t = self.t == other.t

        same_pos = True
        same_vel = True
        for i in range(3):
            if self.pos[i] != other.pos[i]:
                same_pos = False
                break
            if self.vel[i] != other.vel[i]:
                same_vel = False
                break
        same_eclipse = self.eclipse == other.eclipse

        same_critical = self.critical == other.critical

        return (same_agent and same_component_status and same_dod and same_charging_status and same_buffer_in_capacity
                and same_buffer_out_capacity and same_data_rate_in and same_data_rate_out and same_data_rate_tot
                and same_data_buffer_in and same_data_memory and same_data_buffer_out and same_data_capacity
                and same_power_in and same_power_out and same_power_tot and same_energy_capacity and same_energy_stored
                and same_t and same_pos and same_vel and same_eclipse and same_critical)

    def __str__(self):
        """
        Prints state in the following format:
        t,id,rx,ry,rz,vx,vy,vz,eclipse,
        p_in,p_out,p_tot,e_str,e_cap,
        r_in,r_out,r_tot,d_in,d_in_cap,d_out,d_out_cap,d_mem,d_mem_cap
        """
        return f'{self.t},{self.parent_agent.unique_id},' \
               f'{self.pos[0]},{self.pos[1]},{self.pos[2]},' \
               f'{self.vel[0]},{self.vel[1]},{self.vel[2]},' \
               f'{int(self.eclipse == True)},' \
               f'{self.power_in},{self.power_out},{self.power_tot},' \
               f'{self.energy_stored},{self.energy_capacity},' \
               f'{self.data_rate_in},{self.data_rate_out},{self.data_rate_tot},' \
               f'{self.data_buffer_in},{self.buffer_in_capacity},{self.data_buffer_out},{self.buffer_out_capacity},' \
               f'{self.data_memory},{self.data_capacity}'

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

        if not critical:
            all_off = True
            for component in self.parent_agent.platform.component_list:
                if component.is_on():
                    all_off = False
                    break

            if all_off:
                cause = f'All components are off. Agent platform is off-line.'
                critical = True

        return critical, cause