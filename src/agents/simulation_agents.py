import simpy
import orbitpy
from src.agents.components.components import OnBoardComputer, SolarPanelArray, Transmitter
from src.agents.components.instruments import Instrument
from src.agents.agent import AbstractAgent

class SpacecraftAgent(AbstractAgent):
# class SpacecraftAgent():
    def __init__(self, env, name, unique_id, payload, bus_components):
        # if bus_components is None:
        #     component_list = self.design_bus(payload)
        # else:
        #     component_list = []
        #     cdmh_dict = bus_components
        #     component_list.extend(payload))

        super().__init__(env, unique_id, results_dir, component_list, planner)
        self.env = env
        self.name = name
        self.unique_id = unique_id
        self.payload = payload

    def from_dict(d, env):
        name = d.get('name')
        unique_id = d.get('@id')

        # load payload
        payload_dict = d.get('instrument', None)
        if payload_dict is not None:
            if isinstance(payload_dict, list):
                payload = [Instrument.from_dict(x, env) for x in payload_dict]
            else:
                payload = [Instrument.from_dict(payload_dict, env)] 
        else:
            payload = []

        # load components
        bus = d.get('spacecraftBus', None)
        bus_comp_dict = bus.get('components',None)
        if bus_comp_dict:
            # command and data-handling
            cdmh_dict = bus_comp_dict.get('cdmh', None)
            on_board_computer = OnBoardComputer.from_dict(cdmh_dict, env)
            
            # transmitter and reciver
            comms_dict = bus_comp_dict.get('comms', None)
            transmitter = Transmitter.from_dict(comms_dict.get('transmitter', None), env)
            receiver = Transmitter.from_dict(comms_dict.get('receiver', None), env)
            
            # eps system
            eps_dict = bus_comp_dict.get('eps', None)
            solar_panel = SolarPanelArray.from_dict(eps_dict.get('powerGenerator', None), env)
            battery = SolarPanelArray.from_dict(eps_dict.get('powerStorage', None), env)

            bus_components = [on_board_computer, transmitter, receiver, solar_panel, battery]
        else:
            bus_components = []

        return SpacecraftAgent(env, name, unique_id, payload, bus_components)

    def design_bus(self, payload):
        return []

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