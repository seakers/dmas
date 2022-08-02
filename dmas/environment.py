import json
import os
from typing import Union

from simpy import Environment, Event
from simpy.core import SimTime

from orbitpy.mission import Mission, Settings
from orbitpy.grid import Grid
import orbitpy.util

from dmas.agents.agent import AbstractAgent
from dmas.orbit_data import OrbitData


class ScenarioEnvironment(Environment):
    def __init__(self, mission, duration, grid) -> None:
        super().__init__()
        self.duration = duration * 24 * 3600 #convert from days to seconds
        self.mission = mission
        self.grid = grid
        self.orbit_data = dict()
        
    def from_json(d):
        # parse settings            
        mission = Mission.from_json(d)  
        duration = d.get("duration")

        # read grid information
        grid = orbitpy.util.dictionary_list_to_object_list(d.get("grid", None), Grid)

        return ScenarioEnvironment(mission, duration, grid)

    def run(self):
        super().run(self.duration)

    def load_orbit_data(self, user_dir, space_segment, spacecraft_id_list, 
                                ground_segment, ground_segment_id_list, grid):
        data_dir = user_dir + 'orbit_data/'

        changes_to_scenario = False
        with open(user_dir +'MissionSpecs.json', 'r') as scenario_specs:
            if os.path.exists(data_dir + 'MissionSpecs.json'):
                with open(data_dir +'MissionSpecs.json', 'r') as mission_specs:
                    scenario_dict = json.load(scenario_specs)
                    mission_dict = json.load(mission_specs)
                    if scenario_dict != mission_dict:
                        changes_to_scenario = True
            else:
                changes_to_scenario = True

        if len(os.listdir(data_dir)) > len(grid) and not changes_to_scenario:
            print('Orbit data found!')
        else:
            if changes_to_scenario:
                print('Existing orbit data does not match scenario.')
            else:
                print('Orbit data not found.')

            # clear files if they exist
            if os.path.exists(data_dir):
                for f in os.listdir(data_dir):
                    if 'grid' in f:
                        continue
                    if os.path.isdir(os.path.join(data_dir, f)):
                        for h in os.listdir(data_dir + f):
                             os.remove(os.path.join(data_dir, f, h))
                        os.rmdir(data_dir + f)
                    else:
                        os.remove(os.path.join(data_dir, f)) 
                    # os.rmdir(new_dir)
            
            # propagate data and save to orbit data directory
            print("Propagating orbits...")
            self.mission.execute()                
            print("Propagation done!")

            # save specifications of propagation in the orbit data directory
            with open(user_dir +'MissionSpecs.json', 'r') as scenario_specs:
                scenario_dict = json.load(scenario_specs)
                with open(data_dir +'MissionSpecs.json', 'w') as mission_specs:
                    mission_specs.write(json.dumps(scenario_dict, indent=4))

        print('Loading orbit data...')
        # load spacecraft data
        for spacecraft in space_segment:
            self.orbit_data[spacecraft] = OrbitData.from_directory(data_dir,
                                                                   spacecraft_id_list, 
                                                                   ground_segment_id_list, 
                                                                   spacecraft=spacecraft)

        # load ground station data
        # TODO: ADD SUPPORT FOR GROUND STATIONS' ORBIT DATA
        # self.orbit_data[ground_segment] = OrbitData.from_directory(data_dir, 
        #                                                            spacecraft_id_list, 
        #                                                            ground_segment_id_list,
        #                                                            ground_segment=ground_segment)
        print('Done loading orbit data!')

    def is_eclipse(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].is_eclipse(t)

    def get_position(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].get_position(t)

    def get_velocity(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].get_velocity(t)

    def get_next_agent_access(self, src: AbstractAgent, dst: AbstractAgent, t: SimTime):
        return self.orbit_data[src].get_next_agent_access(dst, t)

class SimulationEnvironment(Environment):
    def __init__(self, dir_path, initial_time: SimTime = 0):
        super().__init__(initial_time=initial_time)
        self.agent_list = []
        self.orbit_data = []
        self.results_dir = self.create_results_directory(dir_path)

    def create_results_directory(self, dir_path):
        """
        Creates a utils directory for this particular scenario if it has not been created yet. 
        :return:
        """        
        results_dir = dir_path + '/results/'

        if os.path.isdir(results_dir):
            print( os.listdir(results_dir) )

            for f in os.listdir(results_dir):
                os.remove(os.path.join(results_dir, f)) 
            os.rmdir(results_dir)
        os.mkdir(results_dir)

        return results_dir

    def add_agents(self, agent_list):
        self.agent_list = agent_list
        self.orbit_data = dict.fromkeys(agent_list)
        for agent in agent_list:
            self.orbit_data[agent] = OrbitData(agent)

    def simulate(self, until: Union[SimTime, Event] = None):
        if len(self.agent_list) == 0:
            raise EnvironmentError('No agents loaded to simulation')

        for agent in self.agent_list:
            self.process(agent.live())
            self.process(agent.platform.sim())

        self.run(until)

        for agent in self.agent_list:
            agent.update_system()

        print('SIMULATION DONE')

        # PRINT AGENT STATE HISTORY
        for agent in self.agent_list:
            agent.print_state()
            agent.print_planner_history()

        print('Results printed to: \'' + self.results_dir + '\'')

    def is_eclipse(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].is_eclipse(t)

    def get_position(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].get_position(t)

    def get_velocity(self, agent: AbstractAgent, t: SimTime):
        return self.orbit_data[agent].get_velocity(t)
