import numpy as np
import os
import os.path
import shutil
import pandas as pd
from simpy.core import SimTime
#import orekit

from src.agents.agent import AbstractAgent


class OrbitData:
    def __init__(self, agent: AbstractAgent):
        self.parent_agent = agent
        # self.eclipse_intervals = [(5.5, 10.5)]
        self.eclipse_intervals = []
        self.time_step = 1

        # self.eclipse_intervals = []
        # #get data from files
        # root = os.getcwd() + "/scenarios/orbit_data_test/input"
        # eclipse_data, cartesian_data, step = self.parse_data(root, agent.unique_id)
        #
        # #assign eclipse data
        # self.eclipse_intervals = []
        # for i in eclipse_data:
        #     self.eclipse_intervals.append(i)
        #
        # #assign attitude data
        # self.position = []
        # self.velocity = []
        # for i in cartesian_data:
        #     self.position.append(i[1:4])
        #     self.velocity.append(i[4:])
        # self.time_step = step
        return

    def parse_data(self, root, id):
        agent_folder = "/sat" + str(id)
        eclipse_file = root + agent_folder + "/eclipses.csv"
        cartesian_file = root + agent_folder + "/state_cartesian.csv"
        eclipse_data = pd.read_csv(eclipse_file, skiprows=[0, 1, 2])
        cartesian_data = pd.read_csv(cartesian_file, skiprows=[0, 1, 2, 3])
        a = np.asarray(eclipse_data)
        b = np.asarray(cartesian_data)
        time_str = np.asarray(pd.read_csv(cartesian_file, nrows=3))[1][0]
        x = time_str.split(' ')
        t = x[-1] #step size in seconds --> used to index correct time
        return a, b, t

    def get_next_eclipse(self, t: SimTime):
        #t = int(t * self.time_step)
        for interval in self.eclipse_intervals:
            t_start, t_end = interval
            if t_end <= t:
                continue
            elif t < t_start:
                return t_start
            elif t < t_end:
                return t_end
        return np.Infinity

    def is_eclipse(self, t: SimTime):
        t = int(t*self.time_step)
        for interval in self.eclipse_intervals:
            t_start, t_end = interval
            if t_start <= t < t_end:
                return True
        return False

    def get_position(self, t: SimTime):
        t = int(t * self.time_step)
        # return self.position[t]
        return [-1,-1,-1]

    def get_velocity(self, t: SimTime):
        t = int(t * self.time_step)
        # return self.velocity[t]
        return [-1,-1,-1]