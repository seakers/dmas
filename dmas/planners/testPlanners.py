from dmas.agents.components.components import *
from dmas.agents.components.instruments import Instrument
from dmas.agents.state import State
from dmas.planners.planner import Planner
from dmas.planners.actions import *

"""
This package contains a series of planners meant to test different functionalitites of DMAS. 
They are very scenario-specific and should not be used in other scenarios other than the ones
they were designed for. 
"""

class DataTracking(Planner):
    """
    Scenario:
    There exists only two agents: two satellites in slightly different orbits. The satellite 
    makes no measurements and has no capabilities other than station keeping. Their transmitters 
    have a peak data-rate of 1bps and can only send messages at 10bps each.

    Satellite 1 sends a message while both satellites are visible at time T=754.92s. Since they
    are both visible to one and other during the duration of the transmission, this is completed
    without any problems at time T=764.92s. Satellite 2 then responds at time T=1665.07s, during
    which the satellites are still in view of one and other. However, the access time is not long
    enough to maintain a prolonged connection, which causes the transmission to fail at T=1670.07s.
    Satellite 2 tries again at T=3592.05s, where the access duration is long enough to complete
    the transmission.
    """
    def __init__(self, env, unique_id, knowledge_base=None):
        super().__init__(env,  knowledge_base)
        self.unique_id = unique_id
        self.component_list = []

    def update(self, state, t):
        super().update(state, t)
        platform = state.parent_agent.platform

        if 'sp1' in self.unique_id and t == 0 and len(self.plan) == 0:
            t_start = 162*4.6656879355937875
            
            other_agent = state.parent_agent.other_agents['sp2']

            actuate_on = ActuateComponentAction(platform.transmitter, t_start, status=True)
            transmit = TransmitAction(state.parent_agent, other_agent, t_start, 10, 1, 11)

            actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
            transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

            self.plan[actuate_on] = actuate_on_prc
            self.plan[transmit] = transmit_prc

        # elif 'sp2' in self.unique_id and t == 0 and len(self.plan) == 0:
        #     t_start = 358*4.6656879355937875 - 5
            
        #     other_agent = state.parent_agent.other_agents['sp1']

        #     actuate_on = ActuateComponentAction(platform.transmitter, t_start, status=True)
        #     transmit = TransmitAction(state.parent_agent, other_agent, t_start, 10, 1, 11)

        #     actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
        #     transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

        #     self.plan[actuate_on] = actuate_on_prc
        #     self.plan[transmit] = transmit_prc

    def interrupted_action(self, action: Action, state: State, t):
        super().interrupted_action(action, state, t)

        if self.safe_mode:
            return

        if type(action) == MeasurementAction:
            action_prc = self.env.process(self.schedule_action(action, state, t))
            self.plan[action] = action_prc
        elif type(action) == TransmitAction:
            msg = action.msg
            if t - msg.timeout_start >= msg.timeout and msg.timeout_start > -1:
                actuate_off = ActuateComponentAction(self.transmitter, t, status=False)
                actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
                self.plan[actuate_off] = actuate_off_prc
            else:
                action_prc = self.env.process(self.schedule_action(action, state, t))
                self.plan[action] = action_prc

# class PowerTracking(Planner):
#     def __init__(self, env, unique_id, component_list, scenario_num=1):
#         super().__init__(env)
#         self.unique_id = unique_id
#         self.component_list = []
#         self.scenario_num = scenario_num

#         for component in component_list:
#             self.component_list.append(component)
#             if type(component) == Transmitter:
#                 self.transmitter = component
#             if type(component) == Receiver:
#                 self.receiver = component
#             elif type(component) == OnBoardComputer:
#                 self.on_board_computer = component
#             elif type(component) == PowerGenerator or type(component) == SolarPanelArray:
#                 self.power_generator = component
#             elif type(component) == Battery:
#                 self.battery = component
#             elif type(component) == Instrument:
#                 self.instrument = component

#     def update(self, state, t):
#         super().update(state, t)

#         if t == 0 and len(self.plan) == 0:
#             if 1 <= self.scenario_num <= 2:
#                 t_start = 1
#                 t_end = 8.5
#                 actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
#                 actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
#                 measurement = MeasurementAction([self.instrument], None, t_start, t_end)

#                 actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                 actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
#                 measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

#                 self.plan[actuate_on] = actuate_on_prc
#                 self.plan[actuate_off] = actuate_off_prc
#                 self.plan[measurement] = measurement_prc

#             elif self.scenario_num <= 3:
#                 power_on = ActuatePowerComponentAction(self.power_generator, 1, self.power_generator.max_power_generation)
#                 power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
#                 self.plan[power_on] = power_on_prc

#                 t_start = 8.5
#                 t_end = t_start + 5
#                 actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
#                 actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
#                 measurement = MeasurementAction([self.instrument], None, t_start, t_end)

#                 actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                 actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
#                 measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

#                 self.plan[actuate_on] = actuate_on_prc
#                 self.plan[actuate_off] = actuate_off_prc
#                 self.plan[measurement] = measurement_prc

#             elif self.scenario_num <= 4:
#                 if state.parent_agent.unique_id == 0:
#                     t_start = 1
#                     t_end = 5
#                     actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
#                     actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
#                     measurement = MeasurementAction([self.instrument], None, t_start, t_end)

#                     actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                     actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
#                     measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

#                     self.plan[actuate_on] = actuate_on_prc
#                     self.plan[actuate_off] = actuate_off_prc
#                     self.plan[measurement] = measurement_prc

#                     t_start = 6
#                     other_agent = state.parent_agent.other_agents[0]

#                     actuate_on = ActuateComponentAction(self.transmitter, t_start, status=True)
#                     transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)

#                     actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                     transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

#                     self.plan[actuate_on] = actuate_on_prc
#                     self.plan[transmit] = transmit_prc
#             elif self.scenario_num <= 7.5:
#                 if state.parent_agent.unique_id == 0 or state.parent_agent.unique_id == 1:
#                     t_start = 1
#                     t_end = 5
#                     actuate_on = ActuateComponentAction(self.instrument, t_start, status=True)
#                     actuate_off = ActuateComponentAction(self.instrument, t_end, status=False)
#                     measurement = MeasurementAction([self.instrument], None, t_start, t_end)

#                     actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                     actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
#                     measurement_prc = self.env.process(self.schedule_action(measurement, state, t))

#                     self.plan[actuate_on] = actuate_on_prc
#                     self.plan[actuate_off] = actuate_off_prc
#                     self.plan[measurement] = measurement_prc

#                     t_start = 6

#                     other_agent = None
#                     for agent in state.parent_agent.other_agents:
#                         if agent.unique_id == 2:
#                             other_agent = agent
#                             break

#                     transmit = None
#                     actuate_on = ActuateComponentAction(self.transmitter, t_start, status=True)
#                     if self.scenario <= 5:
#                         transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)
#                     elif self.scenario <= 5.5:
#                         transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 4)
#                     elif self.scenario <= 6:
#                         transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)
#                     elif self.scenario <= 6.5:
#                         transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 4)
#                     elif self.scenario <= 7:
#                         transmit = TransmitAction(state.parent_agent, other_agent, t_start, 4, 1, 10)

#                     actuate_on_prc = self.env.process(self.schedule_action(actuate_on, state, t))
#                     transmit_prc = self.env.process(self.schedule_action(transmit, state, t))

#                     self.plan[actuate_on] = actuate_on_prc
#                     self.plan[transmit] = transmit_prc
#             elif self.scenario_num <= 8:
#             #     turn_on = ActuatePowerComponentAction(self.power_generator, 10.5, 10)
#             #     turn_on_prc = self.env.process(self.schedule_action(turn_on, state, t))
#             #     self.plan[turn_on] = turn_on_prc
#                 return
#             else:
#                 raise ImportError(f'Testing scenario number {self.scenario} not yet supported.')
#         return

    # def interrupted_action(self, action: Action, state: State, t):
    #     super().interrupted_action(action, state, t)

    #     if self.safe_mode:
    #         return

    #     if type(action) == MeasurementAction:
    #         action_prc = self.env.process(self.schedule_action(action, state, t))
    #         self.plan[action] = action_prc
    #     elif type(action) == TransmitAction:
    #         msg = action.msg
    #         if t - msg.timeout_start >= msg.timeout and msg.timeout_start > -1:
    #             actuate_off = ActuateComponentAction(self.transmitter, t, status=False)
    #             delete = DeleteMessageAction(action.msg, t)

    #             actuate_off_prc = self.env.process(self.schedule_action(actuate_off, state, t))
    #             delete_prc = self.env.process(self.schedule_action(delete, state, t))

    #             self.plan[actuate_off] = actuate_off_prc
    #             self.plan[delete] = delete_prc
    #         else:
    #             action_prc = self.env.process(self.schedule_action(action, state, t))
    #             self.plan[action] = action_prc
