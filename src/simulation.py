import json
from simpy import Environment
import os
from orbitpy.util import Spacecraft, GroundStation, SpacecraftBus, OutputInfoUtility, OrbitState
from orbitpy.grid import Grid
import orbitpy

from src.environment import ScenarioEnvironment
from src.agents.simulation_agents import SpacecraftAgent       

class Simulation:
    def __init__(self, user_dir, space_segment = [], ground_segment=None, scenario_environment=None) -> None:
        """
        Initializes a simulation.
        """
        # create agent list
        # -add all satellites in the space segment
        self.agent_list = []
        for spacecraft in space_segment:
            self.agent_list.append(spacecraft)

        # -add ground station
        if ground_segment is not None:
            self.agent_list.append(ground_segment) 

        # assign grid 
        self.grid = []
        self.grid.extend(scenario_environment.grid)

        # create simulation directories
        self.user_dir = user_dir
        self.results_dir = user_dir + 'results/' if os.path.isdir(user_dir + '/results/') else self.create_dir(user_dir, 'results', True)
        self.orbit_data_dir = user_dir + 'orbit_data/' if os.path.isdir(user_dir + '/orbit_data/') else self.create_dir(user_dir, 'orbit_data', True)

        # assign scenario environment
        self.scenario_environment = scenario_environment

    def from_json(user_dir):
        """
        Initializes a simulation from a JSON file
        """
        # initialize mission dictionary
        mission_dict = None
        with open(user_dir +'MissionSpecs.json', 'r') as mission_specs:
            # load json file as dictionary
            mission_dict = json.load(mission_specs)

            # set output directory to orbit data directory
            if mission_dict.get("settings", None) is not None:
                mission_dict["settings"]["outDir"] = user_dir + '/orbit_data/'
            else:
                mission_dict["settings"] = {}
                mission_dict["settings"]["outDir"] = user_dir + '/orbit_data/'

            # creat orbit data directory
            new_dir = user_dir + '/orbit_data/'
            if not os.path.isdir(new_dir):
                os.mkdir(new_dir)   
            

        if mission_dict is None:
            raise ImportError()

        # read scenario information
        scenario_environment = ScenarioEnvironment.from_json(mission_dict)    

        # read space and ground segment information
        custom_spc_dict = mission_dict.get("spacecraft", None)
        constel_dict = mission_dict.get("constellation", None)
        if custom_spc_dict is not None:
            if custom_spc_dict is not None:
                if isinstance(custom_spc_dict, list):
                    space_segment = [SpacecraftAgent.from_dict(x, scenario_environment) for x in custom_spc_dict]
                else:
                    space_segment = [SpacecraftAgent.from_dict(custom_spc_dict, scenario_environment)] 

        elif constel_dict is not None:
            raise IOError('Constallation inputs not yet supported')

        # TODO Add support for ground stations
        # ground_segment = orbitpy.util.dictionary_list_to_object_list(mission_dict.get("groundStation", None), GroundStationAgent)
        ground_segment = None
        
        # return initialized simulation
        return Simulation(user_dir, space_segment, ground_segment, scenario_environment)

    def run(self):
        # checks for agent list
        if len(self.agent_list) == 0:
            raise EnvironmentError('No agents loaded to simulation')

        # perform orbit propagation and coverage analysis
        if len(os.listdir(self.orbit_data_dir)) > len(self.grid):
            print('Orbit data already propagated.')
        else:
            self.scenario_environment.propagate()
        print('Loading orbit data...')
        self.scenario_environment.load_orbit_data(self.orbit_data_dir, self.agent_list)
        print('Done loading orbit data.')

        # initiate agent live process
        for agent in self.agent_list:
            self.scenario_environment.process(agent.live())
            # self.scenario.process(agent.platform.sim())

        # run simulation
        self.scenario_environment.run()

        # perform final system update for all agents        
        for agent in self.agent_list:
            agent.update_system()

    def print_results(self):
        # print agent state hitory
        for agent in self.agent_list:
            # agent.print_state()
            # agent.print_planner_history()
            pass

    def create_dir(self, dir_path: str, dir_name: str, clear=False):
        new_dir = dir_path + '/' + dir_name + '/'

        if os.path.isdir(new_dir) and clear:
            for f in os.listdir(new_dir):
                os.remove(os.path.join(new_dir, f)) 
            os.rmdir(new_dir)
        os.mkdir(new_dir)

        print(f'new directory made at {new_dir}')
        return new_dir

