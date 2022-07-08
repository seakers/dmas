import simpy
from src.agents.agent import AbstractAgent

# class SpacecraftAgent(AbstractAgent):
class SpacecraftAgent():
    def __init__(self, name, unique_id):
        # super().__init__(env, unique_id, results_dir, component_list, planner)
        self.env = None
        self.name = name
        self.unique_id = unique_id

    def from_dict(d):
        name = d.get('name')
        unique_id = d.get('@id')
        return SpacecraftAgent(name, unique_id)

    def set_environment(self, env):
        self.env = env

    def live(self, env):
        self.env = env
        
        print('\nhello world!')
        print('Not much to do now\n3...')
        yield self.env.timeout(1)
        print('2...')
        yield self.env.timeout(1)
        print('1...')
        yield self.env.timeout(1)
        print('...goodnight!\n')

    def update_system(self):
        pass

class GroundStationAgent():
    def __init__(self, d) -> None:
        pass