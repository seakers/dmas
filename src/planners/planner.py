from src.agents.components.components import PowerGenerator
from src.agents.state import State, simpy
from src.planners.actions import *


class Planner:
    def __init__(self, env, knowledge_base=None):
        self.env = env
        self.plan = {}
        self.plan_history = []
        self.active_plan = []
        self.completed_plan = []
        self.interrupted_plan = []
        self.knowledge_base = knowledge_base
        self.safe_mode = False

    def update(self, state: State, t):
        # schedules next actions to be given to agent or reconsiders plan
        # must consider current state, time, knowledge, and previously done or interrupted actions
        p_tot = state.power_tot
        platform = state.parent_agent.platform

        if state.is_critical():
            if p_tot < 0:
                # power deficiency detected
                power_on = None
                if platform.power_generator.power < platform.power_generator.max_power_generation:
                    # if power generator is not up to its maximum power generation, turn on and provide power
                    # power_on = ActuatePowerComponentAction(self.power_generator, t,
                    #                                        -p_tot + self.power_generator.power)
                    dif = platform.power_generator.power - platform.power_generator.max_power_generation
                    if p_tot >= dif:
                        power_on = ActuatePowerComponentAction(platform.power_generator, t,
                                                               -p_tot + platform.power_generator.power)
                        p_tot = 0
                    else:
                        power_on = ActuatePowerComponentAction(platform.power_generator, t,
                                                               -dif + platform.power_generator.power)
                        p_tot -= dif

                    if power_on is not None:
                        power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
                        self.plan[power_on] = power_on_prc

                if platform.battery.power < platform.battery.max_power_generation and p_tot < 0:
                    # else if battery is not up to its maximum power generation, turn on and provide power
                    # power_on = ActuatePowerComponentAction(self.battery, t, -state.power_tot + self.battery.power)

                    dif = platform.battery.power - platform.battery.max_power_generation
                    if p_tot >= dif:
                        power_on = ActuatePowerComponentAction(platform.battery, t,
                                                               -p_tot + platform.battery.power)
                        p_tot = 0
                    else:
                        power_on = ActuatePowerComponentAction(platform.battery, t,
                                                               -dif + platform.battery.power)
                        p_tot -= dif

                    if power_on is not None:
                        power_on_prc = self.env.process(self.schedule_action(power_on, state, t))
                        self.plan[power_on] = power_on_prc


            elif state.power_tot > 0:
                # power surplus
                power_off = None
                if (platform.battery.energy_stored.level / platform.battery.energy_capacity < 0.70
                        and platform.battery.power < state.power_tot and not platform.battery.is_charging()):
                    # if battery not up to capacity, charge batteries
                    start = t
                    dt = (platform.battery.energy_capacity - platform.battery.energy_stored.level) / \
                         (state.power_tot - platform.battery.power)
                    # dt = 3
                    end = start + dt

                    power_off = ChargeAction(start, end)

                elif platform.battery.power > 0:
                    # else lower battery power output
                    power = platform.battery.power - state.power_tot
                    power_off = ActuatePowerComponentAction(platform.battery, t, power)

                elif platform.power_generator.power > 0:
                    # else if batteries are off, lower power generator output
                    power = platform.power_generator.power - state.power_tot
                    power_off = ActuatePowerComponentAction(platform.power_generator, t, power)

                if power_off is not None:
                    power_off_prc = self.env.process(self.schedule_action(power_off, state, t))
                    self.plan[power_off] = power_off_prc

    def schedule_action(self, action: Action, state: State, t_curr):
        try:
            self.plan_history.append(action)

            duration = action.start - t_curr
            if duration < 0:
                duration = 0

            yield self.env.timeout(duration)

            state.parent_agent.plan.put(action)
        except simpy.Interrupt as i:
            return

    def completed_action(self, action: Action, state: State, t):
        if type(action) == TransmitAction:
            delete = DeleteMessageAction(action.msg, t)
            delete_prc = self.env.process(self.schedule_action(delete, state, t))
            self.plan[delete] = delete_prc

        action.complete()
        self.plan.pop(action)
        self.completed_plan.append((action, t))

    def interrupted_action(self, action: Action, state: State, t):
        self.plan.pop(action)
        self.interrupted_plan.append((action, t))

    def interrupted_message(self, msg, state: State, t):
        pass

    def timed_out_message(self, msg, state: State, t):
        pass

    def message_received(self, msg, state: State, t):
        delete = DeleteMessageAction(msg, t)
        self.schedule_action(delete, state, t)

    def message_deleted(self, msg, t):
        pass

    def update_knowledge_base(self, measurement_results):
        pass

    def enter_safe_mode(self):
        self.safe_mode = True
        self.clear_plan()

    def exit_safe_mode(self):
        self.safe_mode = False

    def clear_plan(self):
        while len(self.plan) > 0:
            action, process = self.plan.popitem()
            if not process.triggered:
                process.interrupt('clearing plan')
