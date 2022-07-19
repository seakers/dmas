import simpy
import orbitpy
from dmas.planners.planner import Planner
from dmas.agents.components.components import OnBoardComputer, Receiver, SolarPanelArray, Transmitter, Battery
from dmas.agents.components.instruments import Instrument
from dmas.agents.agent import AbstractAgent

class SpacecraftAgent(AbstractAgent):
# class SpacecraftAgent():
    def __init__(self, env, name, unique_id, payload, bus_components, planner, results_dir):
        self.name = name
        self.payload = payload

        if len(bus_components) < 1:
            bus_components = self.design_bus(payload)

        component_list = []
        component_list.extend(payload)
        component_list.extend(bus_components)

        super().__init__(env, unique_id, results_dir, component_list, planner)

    def from_dict(d, env, results_dir):
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
        bus_dict = d.get('spacecraftBus', None)
        bus_comp_dict = bus_dict.get('components',None)
        if bus_comp_dict:
            # command and data-handling
            cmdh_dict = bus_comp_dict.get('cmdh', None)
            on_board_computer = OnBoardComputer.from_dict(cmdh_dict, env)
            
            # transmitter and reciver
            comms_dict = bus_comp_dict.get('comms', None)
            transmitter = Transmitter.from_dict(comms_dict.get('transmitter', None), env)
            receiver = Receiver.from_dict(comms_dict.get('receiver', None), env)
            
            # eps system
            eps_dict = bus_comp_dict.get('eps', None)
            solar_panel = SolarPanelArray.from_dict(eps_dict.get('powerGenerator', None), env)
            battery = Battery.from_dict(eps_dict.get('powerStorage', None), env)

            bus_components = [on_board_computer, transmitter, receiver, solar_panel, battery]
        else:
            bus_components = []

        planner_dict = d.get('planner', None)
        planner_type = planner_dict.get('@type', None)
        if 'STATION_KEEPING' in planner_type:
            planner = Planner(env)
        else:
            raise Exception(f'Planner of type {planner_type} not yet suppoerted')

        return SpacecraftAgent(env, name, unique_id, payload, bus_components, planner, results_dir)

    def design_bus(self, payload):
        raise Exception('Automated satellite bus design not yet supported')
        return []

    def set_environment(self, env):
        self.env = env

    # def live(self):
    #     print('\nhello world!')
    #     print('Not much to do now\n3...')
    #     yield self.env.timeout(1)
    #     print('2...')
    #     yield self.env.timeout(1)
    #     print('1...')
    #     yield self.env.timeout(1)
    #     print('...goodnight!\n')

    # def update_system(self):
    #     pass

class GroundStationAgent():
    def __init__(self, d) -> None:
        pass