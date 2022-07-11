import simpy
import orbitpy
from src.agents.components.instruments import Instrument
from src.agents.agent import AbstractAgent

# class SpacecraftAgent(AbstractAgent):
class SpacecraftAgent():
    def __init__(self, env, name, unique_id, payload):
        # super().__init__(env, unique_id, results_dir, component_list, planner)
        self.env = env
        self.name = name
        self.unique_id = unique_id
        self.payload = payload

    def from_dict(d, env):
        name = d.get('name')
        unique_id = d.get('@id')

        payload_dict = d.get('instrument', None)
        if payload_dict is not None:
            if isinstance(payload_dict, list):
                payload = [Instrument.from_dict(x, env) for x in payload_dict]
            else:
                payload = [Instrument.from_dict(payload_dict, env)] 
        else:
            payload = []

        return SpacecraftAgent(env, name, unique_id, payload)

    def set_environment(self, env):
        self.env = env

    def live(self):
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