import logging
import os

import numpy as np

from dmas.agents.components.components import *
from dmas.planners.actions import ActuateAgentAction


class Platform:
    def __init__(self, parent_agent, env, component_list):
        self.parent_agent = parent_agent
        self.env = env

        # logger
        self.logger = self.setup_platform_logger()

        # platform status
        self.alive = True

        # component list
        self.component_list = component_list
        self.transmitter = None
        self.receiver = None
        self.on_board_computer = None
        self.power_generator = None
        self.battery = None

        for component in component_list:
            if type(component) == Transmitter:
                self.transmitter = component
            if type(component) == Receiver:
                self.receiver = component
            elif type(component) == OnBoardComputer:
                self.on_board_computer = component
            elif type(component) == PowerGenerator or type(component) == SolarPanelArray:
                self.power_generator = component
            elif type(component) == Battery:
                self.battery = component

        if (self.transmitter is None or self.receiver is None or self.on_board_computer is None
                or self.power_generator is None or self.battery is None):
            raise Exception('Agent requires at least one of each of the following components:'
                            ' transmitter, receiver, on-board computer, power generator, and battery')

        # orbital information
        self.pos = [-1, -1, -1]
        self.vel = [-1, -1, -1]
        self.eclipse = False

        # events
        self.agent_update = simpy.Event(env)
        self.updated_periodically = simpy.Event(env)
        self.updated_manually = simpy.Event(env)
        self.critical_state = simpy.Event(env)

        self.t_prev = self.env.now
        self.t_crit = -1
        self.event_tracker = None

    def sim(self):
        critical_state_check = self.env.process(self.wait_for_critical_state())
        eclipse_event = self.env.process(self.wait_for_eclipse_event())
        periodic_update = self.env.process(self.periodic_update())

        # self.updated_manually.succeed()
        while True:
            yield critical_state_check | self.critical_state | eclipse_event | self.agent_update | periodic_update
            if self.updated_manually.triggered:
                self.updated_manually = simpy.Event(self.env)

            # update component status
            if not self.is_critical():
                t_curr = self.env.now
                self.update(t_curr)

            # inform agent of critical event
            if ((critical_state_check.triggered 
                or eclipse_event.triggered 
                or self.is_critical())
                    and self.parent_agent.alive):
                
                if not self.parent_agent.critical_state.triggered:
                    self.parent_agent.system_check('Platform flagged a new event.')

            # if critical state persists after 1 time-step, kill platform and agent
            if self.is_critical() and 0 < (self.env.now -  self.t_crit) <= 1 and self.t_crit >= 0:
                self.logger.debug(f'T{self.env.now}:\tCritical state persisting. Platform going off-line...')

                # turn off all components
                for component in self.component_list:
                    if component.is_on():
                        self.logger.debug(f'T{self.env.now}:\tTurning off {component.name}...')
                        component.turn_off()

                # terminate all background processes
                if not critical_state_check.triggered:
                    critical_state_check.interrupt('Platform off-line.')
                if not eclipse_event.triggered:
                    eclipse_event.interrupt('Platform off-line.')
                if not periodic_update.triggered:
                    periodic_update.interrupt('Platform off-line.')

                # flag agent for status
                self.parent_agent.system_check('Platform flagged a critical state.')
                break
            elif self.is_critical():
                self.t_crit = self.env.now
            else:
                self.t_crit = -1

            if eclipse_event.triggered:
                if self.eclipse:
                    self.logger.debug(f'T{self.env.now}:\tEclipse event started!')
                else:
                    self.logger.debug(f'T{self.env.now}:\tEclipse event ended!')


            # reset parallel processes as needed
            if not critical_state_check.triggered:
                critical_state_check.interrupt()
                yield critical_state_check
            critical_state_check = self.env.process(self.wait_for_critical_state())

            if not eclipse_event.triggered:
                eclipse_event.interrupt()
                yield eclipse_event
            eclipse_event = self.env.process(self.wait_for_eclipse_event())

            if self.critical_state.triggered:
                self.critical_state = simpy.Event(self.env)

            if self.agent_update.triggered:
                self.agent_update = simpy.Event(self.env)

            # self.updated_manually.succeed()

    def update(self, t):
        # print(f'Performed system update at T{t}')
        self.updated_manually = simpy.Event(self.env)

        dt = t - self.t_prev

        # count power and data usage
        power_in, power_out, power_tot, data_rate_in = self.count_usage()

        # update values
        # -data
        if data_rate_in * dt > 0:
            dD = self.on_board_computer.data_capacity - self.on_board_computer.data_stored.level
            if dD > data_rate_in * dt:
                self.on_board_computer.data_stored.put(data_rate_in * dt)
            else:
                self.on_board_computer.data_stored.put(dD)

        if (self.transmitter.data_rate * dt > 0
                and self.transmitter.data_stored.level > 0
                and self.transmitter.is_transmitting()):
            if self.transmitter.data_stored.level >= self.transmitter.data_rate * dt:
                self.transmitter.data_stored.get(self.transmitter.data_rate * dt)
            else:
                self.transmitter.data_stored.get(self.transmitter.data_stored.level)

        # -power
        self.battery.update_charge(power_tot, dt)

        # -orbital information
        self.eclipse = self.env.is_eclipse(self.parent_agent, t)
        self.pos = self.env.get_position(self.parent_agent, t)
        self.vel = self.env.get_velocity(self.parent_agent, t)

        # update component capabilities
        if type(self.power_generator) == SolarPanelArray:
            if self.eclipse and not self.power_generator.in_eclipse():
                self.parent_agent.system_check('Platform is about to enter eclipse.')
                self.power_generator.enter_eclipse()
            elif not self.eclipse and self.power_generator.in_eclipse():
                self.parent_agent.system_check('Platform is about to exit eclipse.')
                self.power_generator.exit_eclipse()

        if (1 - self.battery.energy_stored.level / self.battery.energy_capacity) >= self.battery.dod:
            self.battery.can_hold_charge = False
            if self.battery.is_charging:
                self.battery.turn_off_charge()

        # update times
        self.t_prev = t
        self.updated_manually.succeed()

        # check for critical state
        if self.is_critical() and not self.critical_state.triggered:
            self.critical_state.succeed()
        elif self.is_critical():
            self.t_crit = -1

        self.logger.debug(f'T{t}:\t{str(self)}')

    def is_critical(self):
        # count power and data usage
        power_in, power_out, power_tot, data_rate_in = self.count_usage()

        critical = False

        if self.battery.energy_stored.level == self.battery.energy_capacity and self.battery.charging:
            # Battery is full and is still charging.
            critical = True
        elif power_tot < 0:
            # Insufficient power being generated
            critical = True
        elif power_tot > 0 and not self.battery.charging:
            # Excess power being generated and is not being used for charging
            critical = True
        elif self.on_board_computer.data_stored.level == self.on_board_computer.data_capacity and data_rate_in > 0:
            # On-board memory full and data is coming in faster than it is leaving.
            critical = True

        return critical

    def periodic_update(self):
        try:
            self.updated_periodically.succeed()
            while True:
                yield self.env.timeout(1)
                if self.updated_periodically.triggered:
                    self.updated_periodically = simpy.Event(self.env)

                # update component status
                t_curr = self.env.now
                self.update(t_curr)

                self.updated_periodically.succeed()
        except simpy.Interrupt as i:
            return

    def wait_for_critical_state(self):
        """
        Predicts next critical state and waits for it to arrive.
        Critical states include charging while battery is full and not being used, battery charge dropping below the
        accepted depth of discharge, data coming in with a full memory that is not being depleted, and empty memory
        being depleted.
        """
        dt_min = np.Infinity

        # count power and data usage
        data_rate_in = 0
        power_out = 0
        power_in = 0
        for component in self.component_list:
            if component.is_on():
                if component.power <= 0:
                    power_out -= component.power
                if type(component) != Receiver and type(component) != Transmitter:
                    data_rate_in += component.data_rate
                if type(component) == Battery or type(component) == PowerGenerator:
                    power_in += component.power
        power_tot = power_in - power_out

        # check when battery charge will reach its full capacity
        # if self.battery.is_charging():
        #     dx = self.battery.energy_capacity - self.battery.energy_stored.level
        #     dxdt = power_tot - self.battery.power
        #     if dxdt > 0:
        #         dt = dx / dxdt
        #         if dt < dt_min:
        #             dt_min = dt

        # check when battery charge will be below DOD
        if self.battery.is_on():
            dx = self.battery.energy_capacity * (
                    1 - self.battery.dod) - self.battery.energy_stored.level
            dxdt = power_tot - self.battery.power
            dt = dx / dxdt
            if dt > 0:
                if dt < dt_min:
                    dt_min = dt

        # check when memory will fill up
        dx = self.on_board_computer.data_capacity - self.on_board_computer.data_stored.level
        dxdt = data_rate_in + self.receiver.data_rate - self.transmitter.data_rate
        if dxdt > 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        # check when memory will empty
        dx = -self.on_board_computer.data_stored.level
        dxdt = data_rate_in + self.receiver.data_rate - self.transmitter.data_rate
        if dxdt < 0:
            dt = dx / dxdt
            if dt < dt_min:
                dt_min = dt

        try:
            self.logger.debug(f'T{self.t_prev}:\tNext projected critical state will be at T{self.env.now + dt_min}.')
            yield self.env.timeout(dt_min)
        except simpy.Interrupt as i:
            return

    def wait_for_eclipse_event(self):
        """
        Predicts next eclipse event and waits for it to arrive.
        :return:
        """
        try:
            t = self.env.now
            t_eclipse = self.env.orbit_data[self.parent_agent].get_next_eclipse(t)
            dt = t_eclipse - t
            self.logger.debug(f'T{self.t_prev}:\tNext projected eclipse event will be at T{t_eclipse}.')
            yield self.env.timeout(dt)
        except simpy.Interrupt as i:
            return

    def count_usage(self):
        # count power and data usage
        data_rate_in = 0
        power_out = 0
        power_in = 0
        for component in self.component_list:
            if component.is_on():
                if component.power <= 0:
                    power_out -= component.power
                if type(component) != Receiver and type(component) != Transmitter:
                    data_rate_in += component.data_rate
                if (type(component) == Battery
                        or type(component) == PowerGenerator
                        or type(component) == SolarPanelArray):
                    power_in += component.power
        power_tot = power_in - power_out

        return power_in, power_out, power_tot, data_rate_in

    def __str__(self):
        """
        Prints platform state in the following format:
        t,id,rx,ry,rz,vx,vy,vz,eclipse,
        p_in,p_out,p_tot,e_str,e_cap,
        r_in,r_out,r_tot,d_in,d_in_cap,d_out,d_out_cap,d_mem,d_mem_cap
        :return:
        """

        # count power and data usage
        power_in, power_out, power_tot, data_rate_in = self.count_usage()

        return f'{self.t_prev},{self.parent_agent.unique_id},' \
               f'{self.pos[0]},{self.pos[1]},{self.pos[2]},' \
               f'{self.vel[0]},{self.vel[1]},{self.vel[2]},' \
               f'{int(self.eclipse == True)},' \
               f'{power_in},{power_out},{power_tot},{self.battery.energy_stored.level},' \
               f'{self.battery.energy_capacity},{data_rate_in},{self.transmitter.data_rate},' \
               f'{data_rate_in - self.transmitter.data_rate},{self.receiver.data_stored.level},' \
               f'{self.receiver.data_capacity},{self.transmitter.data_stored.level},{self.transmitter.data_capacity},' \
               f'{self.on_board_computer.data_stored.level},{self.on_board_computer.data_capacity}'
    
    def setup_platform_logger(self):
        """
        Sets up logger for this platform simulator
        :param agent: parent agent for this platform
        :return:
        """
        results_dir = self.parent_agent.results_dir
        unique_id = self.parent_agent.unique_id

        logger = logging.getLogger(f'P{unique_id}')
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(name)s-%(message)s')

        file_handler = logging.FileHandler(results_dir + f'P{unique_id}.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger