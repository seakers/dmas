import simpy
from agents.agent import AbstractAgent

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

        print('hello world!')
        print('dying in 3...')
        yield self.env.timeout(1)
        print('2...')
        yield self.env.timeout(1)
        print('1...')
        yield self.env.timeout(1)
        print('goodnight!')

class GroundStationAgent():
    def __init__(self, d) -> None:
        pass