import re
import numpy as np
import os
import os.path
import shutil
import pandas as pd
from simpy.core import SimTime
#import orekit

from dmas.agents.agent import AbstractAgent

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
    def __init__(self, agent: AbstractAgent, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data):
        self.parent_agent = agent
        
        self.time_step = time_data['time step']
        self.epoc_type = time_data['epoc type']
        self.epoc = time_data['epoc']

        self.eclipse_data = eclipse_data
        self.position_data = position_data
        self.isl_data = isl_data
        self.gs_access_data = gs_access_data
        self.gp_access_data = gp_access_data

    def from_directory(dir, spacecraft_id_list, ground_station_id_list, spacecraft=None, ground_station=None):
        if spacecraft is not None:
            # data is from a satellite
            id = str(spacecraft_id_list.index(spacecraft.unique_id))
            agent_folder = "sat" + id + '/'

            # load eclipse data
            eclipse_file = dir + agent_folder + "eclipses.csv"
            eclipse_data = pd.read_csv(eclipse_file, skiprows=range(3))
            
            # load position data
            position_file = dir + agent_folder + "state_cartesian.csv"
            position_data = pd.read_csv(position_file, skiprows=range(4))

            # load propagation time data
            time_data =  pd.read_csv(position_file, nrows=3)
            _, epoc_type, _, epoc = time_data.at[0,time_data.axes[1][0]].split(' ')
            epoc_type = epoc_type[1 : -1]
            epoc = float(epoc)
            _, _, _, _, time_step = time_data.at[1,time_data.axes[1][0]].split(' ')
            time_step = float(time_step)

            time_data = { "epoc": epoc, 
                          "epoc type": epoc_type, 
                          "time step": time_step }

            # load inter-satellite link data
            isl_data = dict()
            for file in os.listdir(dir + '/comm/'):                
                isl = re.sub(".csv", "", file)
                sender, _, receiver = isl.split('_')

                if 'sat' + id in sender or 'sat' + id in receiver:
                    isl_file = dir + 'comm/' + file
                    if 'sat' + id in sender:
                        receiver_index = int(re.sub("[^0-9]", "", receiver))
                        receiver_id = spacecraft_id_list[receiver_index]
                        isl_data[receiver_id] = pd.read_csv(isl_file, skiprows=range(3))
                    else:
                        sender_index = int(re.sub("[^0-9]", "", sender))
                        sender_id = spacecraft_id_list[sender_index]
                        isl_data[sender_id] = pd.read_csv(isl_file, skiprows=range(3))

            # load ground station access data
            gs_access = dict()
            for file in os.listdir(dir + agent_folder):
                if 'gndStn' in file:
                    gs_access_file = dir + agent_folder + file
                    gndStation, _ = file.split('_')
                    gndStation_index = int(re.sub("[^0-9]", "", gndStation))
                    gndStation_id = ground_station_id_list[gndStation_index]
                    gs_access[gndStation_id] = pd.read_csv(gs_access_file, skiprows=range(3))

            # load and coverage data metrics data
            gp_access = dict()
            for instrument in spacecraft.payload:
                i_ins = spacecraft.payload.index(instrument)
                gp_acces_by_mode = []

                for mode in instrument.modes:
                    i_mode = instrument.modes.index(mode)
                    gp_acces_by_grid = dict()

                    for grid in spacecraft.env.grid:
                        i_grid = spacecraft.env.grid.index(grid)

                        access_file = dir + agent_folder + f'access_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                        access_data = pd.read_csv(access_file, skiprows=range(4))

                        metrics_file = dir + agent_folder + f'datametrics_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                        metrics_data = pd.read_csv(metrics_file, skiprows=range(4))

                        gp_acces_by_grid[grid]=[access_data, metrics_data]
                    
                    gp_acces_by_mode.append(gp_acces_by_grid)

                gp_access[instrument] = gp_acces_by_mode
            
        return OrbitData(spacecraft, time_data, eclipse_data, position_data, isl_data, gs_access, gp_access)
    
    def get_next_isl_access(self, target, t):
        return [-np.Infinity, np.Infinity]

    def get_next_gs_access(self, t):
        return [-np.Infinity, np.Infinity]

    def get_next_gp_access(self, grid_id, target_index, t):
        return [-np.Infinity, np.Infinity]

    def get_next_eclipse(self, t: SimTime):
        t = int(t * self.time_step)
        for _, row in self.eclipse_data.iterrows():
            t_start = row['start index'] * self.time_step
            t_end = row['end index'] * self.time_step
            if t_end <= t:
                continue
            elif t < t_start:
                return t_start
            elif t < t_end:
                return t_end
        return np.Infinity

    def is_eclipse(self, t: SimTime):
        t = int(t*self.time_step)
        for _, row in self.eclipse_data.iterrows():
            t_start = row['start index'] * self.time_step
            t_end = row['end index'] * self.time_step
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