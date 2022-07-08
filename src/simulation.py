import json
from simpy import Environment
import os
from orbitpy.util import Spacecraft, GroundStation, SpacecraftBus, OutputInfoUtility, OrbitState
import orbitpy

from src.environment import ScenarioEnvironment
from src.agents.simulation_agents import SpacecraftAgent       

class Simulation:
    def __init__(self, user_dir, space_segment = [], ground_segment=[], scenario_environment=None) -> None:
        """
        Initializes a simulation.
        """
        self.agent_list = []
        for spacecraft in space_segment:
            self.agent_list.append(spacecraft)

        # TODO Add support for ground stations
        # for ground_station in ground_segment:
        #     self.agent_list.append(ground_station)

        self.user_dir = user_dir
        self.scenario_environment = scenario_environment

    def from_json(user_dir):
        """
        Initializes a simulation from a JSON file
        """
        mission_dict = None
        with open(user_dir +'MissionSpecs.json', 'r') as mission_specs:
            mission_dict = json.load(mission_specs)

            if mission_dict.get("settings", None) is not None:
                mission_dict["settings"]["outDir"] = user_dir # force change of user-dir
            else:
                mission_dict["settings"] = {}
                mission_dict["settings"]["outDir"] = user_dir

        if mission_dict is None:
            raise ImportError()

        date_dict = mission_dict.get('epoch') if mission_dict.get('epoch') is not None else {"@type":"JULIAN_DATE_UT1", "jd":2459270.5} # 25 Feb 2021 0:0:0 default startDate
        epoch = OrbitState.date_from_dict(date_dict) 
        duration = mission_dict.get('duration') if mission_dict.get('duration') is not None else 1

        custom_spc_dict = mission_dict.get("spacecraft", None)
        constel_dict = mission_dict.get("constellation", None)
        if custom_spc_dict is not None:
            space_segment = orbitpy.util.dictionary_list_to_object_list(custom_spc_dict, SpacecraftAgent)
        elif constel_dict is not None:
            raise IOError('Constallation inputs not yet supported')

        # TODO Add support for ground stations
        # ground_segment = orbitpy.util.dictionary_list_to_object_list(mission_dict.get("groundStation", None), GroundStationAgent)
        ground_segment = None

        scenario_environment = ScenarioEnvironment.from_json(mission_dict)        
        
        return Simulation(user_dir, space_segment, ground_segment, scenario_environment)

    def run(self):
        # create results directory
        self.results_dir = self.create_results_directory()

        # checks for agent list
        if len(self.agent_list) == 0:
            raise EnvironmentError('No agents loaded to simulation')

        # run simulation
        for agent in self.agent_list:
            agent.set_environment(self.scenario_environment)
            self.scenario_environment.process(agent.live())
            # self.scenario.process(agent.platform.sim())

        self.scenario_environment.run()

        # for agent in self.agent_list:
        #     agent.update_system()

    def print_results(self):
        # print agent state hitory
        for agent in self.agent_list:
            # agent.print_state()
            # agent.print_planner_history()
            pass

    def create_results_directory(self):
        """
        Creates a utils directory for this particular simulation if it has not been created yet. 
        :return:
        """        
        results_dir = self.user_dir + '/results/'

        if os.path.isdir(results_dir):
            print( os.listdir(results_dir) )

            for f in os.listdir(results_dir):
                os.remove(os.path.join(results_dir, f)) 
            os.rmdir(results_dir)
        os.mkdir(results_dir)

        return results_dir
    