import numpy as np

from src.agents.state import State


class StatePredictor:
    def predict_state(self, init_state: State, t_f):
        """
        predicts future state at time t
        :param init_state: initial state
        :param t_f: time to which the state is to be propagated
        :return:
        """
        pass

    def predict_next_critical_sate(self, init_state: State):
        """
        predicts next critical state
        :param init_state:
        :return: time in which the critical state will be achieved
        """
        data_rate_in, data_rate_out, data_rate_tot, \
        data_buffer_in, data_buffer_out, data_memory, data_capacity, \
        power_in, power_out, power_tot, energy_stored, energy_capacity, \
        t, critical, isOn = init_state.get_latest_state()

        dt_min = np.Infinity
        parent_agent = init_state.parent_agent

        # check when battery will reach full charge
        if parent_agent.battery.is_charging():
            dx = parent_agent.battery.energy_capacity - parent_agent.battery.energy_stored.level
            dxdt = power_tot - parent_agent.battery.power
            if dxdt > 0:
                dt = dx / dxdt
                if dt < dt_min:
                    dt_min = dt

        # check when battery will go below DOD
        if parent_agent.battery.is_on():
            dx = parent_agent.battery.energy_capacity * (1 - parent_agent.battery.dod) - parent_agent.battery.energy_stored.level
            dxdt = power_tot - parent_agent.battery.power
            dt = dx / dxdt
            if dt > 0:
                if dt < dt_min:
                    dt_min = dt

        # check when memory will fill up
        dx = parent_agent.on_board_computer.data_capacity - parent_agent.on_board_computer.data_stored.level
        dxdt = data_rate_in + parent_agent.receiver.data_rate - parent_agent.transmitter.data_rate
        if dxdt > 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        # check when memory will empty
        dx = -parent_agent.on_board_computer.data_stored.level
        dxdt = data_rate_in + parent_agent.receiver.data_rate - parent_agent.transmitter.data_rate
        if dxdt < 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        return dt_min