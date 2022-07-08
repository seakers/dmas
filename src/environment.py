import os
from typing import Union

from simpy import Environment, Event
from simpy.core import SimTime

from orbitpy.mission import Mission, Settings

from src.agents.agent import AbstractAgent
from src.orbit_data import OrbitData


class ScenarioEnvironment(Environment):
    def __init__(self, mission, duration) -> None:
        super().__init__()
        self.duration = duration * 24 * 3600 #convert from days to seconds
        self.mission = mission
        self.orbit_data = dict()
        
    def from_json(d):
        # parse settings            
        mission = Mission.from_json(d)  
        duration = d.get("duration")
        return ScenarioEnvironment(mission, duration)

    def run(self):
        super().run(self.duration)

    def propagate(self):
        print("Propagating orbits...")
        orbit_data = self.mission.execute()
        print("Propagation done!")

    def load_orbit_data(self, data_dir, agent_list):
        for agent in agent_list:
            self.orbit_data[agent] = OrbitData.from_directory(data_dir, agent.unique_id)
        

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
