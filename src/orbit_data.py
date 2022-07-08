import re
import numpy as np
import os
import os.path
import shutil
import pandas as pd
from simpy.core import SimTime
#import orekit

from src.agents.agent import AbstractAgent

class TimeInterval:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        if self.end < self.start:
            raise Exception('The end of time interval must be later than beginning of the interval.')

    def is_before(self, t):
        return t < self.start

    def is_after(self, t):
        return self.end < t

    def is_during(self, t):
        return self.start <= t <= self.end

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

    def from_directory(dir, unique_id):
        if 'sp' in unique_id:
            # data is from a satellite
            id = re.sub("[^0-9]", "", unique_id)
            agent_folder = "sat" + str(id) + '/'

            # load eclipse data
            eclipse_file = dir + agent_folder + "eclipses.csv"
            eclipse_data = pd.read_csv(eclipse_file, skiprows=range(3))
            
            # load position data
            position_file = dir + agent_folder + "state_cartesian.csv"
            position_data = pd.read_csv(position_file, skiprows=range(4))

            time_data =  pd.read_csv(position_file, nrows=3)
            _, epoc_type, _, epoc = time_data.at[0,time_data.axes[1][0]].split(' ')
            epoc_type = epoc_type[1 : -1]
            epoc = float(epoc)

            _, _, _, _, step_size = time_data.at[1,time_data.axes[1][0]].split(' ')
            step_size = float(step_size)

            # load inter-satellite link data
            isl_data = dict()
            for file in os.listdir(dir + '/comm/'):                
                isl = re.sub(".csv", "", file)
                sender, _, receiver = isl.split('_')

                if 'sat' + str(id) in sender or 'sat' + str(id) in receiver:
                    isl_file = dir + 'comm/' + file
                    if 'sat' + str(id) in sender:
                        receiver = re.sub("[^0-9]", "", receiver)
                        isl_data['sp'+receiver] = pd.read_csv(isl_file, skiprows=range(3))
                    else:
                        sender = re.sub("[^0-9]", "", sender)
                        isl_data['sp'+sender] = pd.read_csv(isl_file, skiprows=range(3))

            # load ground station access data
            gs_access = dict()
            for file in os.listdir(dir + agent_folder):
                if 'gndStn' in file:
                    gs_access_file = dir + agent_folder + file
                    gndStation, _ = file.split('_')
                    id = re.sub("[^0-9]", "", gndStation)
                    gs_access['gs'+str(id)] = pd.read_csv(gs_access_file, skiprows=range(3))

            # load coverage data
            

            # load data metrics data
            x = 1
        pass

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