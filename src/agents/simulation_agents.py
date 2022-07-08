import simpy
from src.agents.agent import AbstractAgent

# class SpacecraftAgent(AbstractAgent):
class SpacecraftAgent():
    def __init__(self, name):
        # super().__init__(env, unique_id, results_dir, component_list, planner)
        self.env = None
        self.name = name

    def from_dict(d):
        name = d.get('name')
        return SpacecraftAgent(name)

    def set_environment(self, env):
        self.env = env

    def live(self):
        if self.env is None:
            raise simpy.Interrupt(f'No environment set for Agent {self.name}')

        print('\nhello world!')
        print('Not much to do now\n3...')
        yield self.env.timeout(1)
        print('2...')
        yield self.env.timeout(1)
        print('1...')
        yield self.env.timeout(1)
        print('...goodnight!\n')

class GroundStationAgent():
    def __init__(self, d) -> None:
        pass