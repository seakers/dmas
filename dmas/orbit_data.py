import re
import numpy as np
import os
import os.path
import shutil
import pandas as pd
from simpy.core import SimTime
from dmas.agents.simulation_agents import SpacecraftAgent

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

        self.eclipse_data = eclipse_data.sort_values(by=['start index'])
        self.position_data = position_data.sort_values(by=['time index'])

        self.isl_data = {}
        for satellite_name in isl_data.keys():
            self.isl_data[satellite_name] = isl_data[satellite_name].sort_values(by=['start index'])

        self.gs_access_data = gs_access_data.sort_values(by=['start index'])
        
        self.gp_access_data = {}
        for instrument in gp_access_data.keys():
            self.gp_access_data[instrument] = []
            for mode in range(len(gp_access_data[instrument])):
                self.gp_access_data[instrument].append(gp_access_data[instrument][mode].sort_values(by=['time index']))
        x = 1

    def from_directory(dir, spacecraft_id_list, ground_segment_id_list, spacecraft=None, ground_segment=None):
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
            gs_access = pd.DataFrame(columns=['start index', 'end index', 'gndStn id'])
            for file in os.listdir(dir + agent_folder):
                if 'gndStn' in file:
                    gndStn_access_file = dir + agent_folder + file
                    gndStn_access_data = pd.read_csv(gndStn_access_file, skiprows=range(3))
                    nrows, _ = gndStn_access_data.shape

                    if nrows > 0:
                        gndStn, _ = file.split('_')
                        gndStn_index = int(re.sub("[^0-9]", "", gndStn))
                        gndStn_id = ground_segment_id_list[gndStn_index]
                        gndStn_id_column = [gndStn_id] * nrows
                        gndStn_access_data['gndStn id'] = gndStn_id_column

                        if len(gs_access) == 0:
                            gs_access = gndStn_access_data
                        else:
                            gs_access = pd.concat([gs_access, gndStn_access_data])

            # load and coverage data metrics data
            gp_access = dict()
            for instrument in spacecraft.payload:
                i_ins = spacecraft.payload.index(instrument)
                gp_acces_by_mode = []

                for mode in instrument.modes:
                    i_mode = instrument.modes.index(mode)
                    gp_acces_by_grid = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]',
                                                             'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                    for grid in spacecraft.env.grid:
                        i_grid = spacecraft.env.grid.index(grid)
                        metrics_file = dir + agent_folder + f'datametrics_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                        metrics_data = pd.read_csv(metrics_file, skiprows=range(4))
                        
                        nrows, _ = metrics_data.shape
                        grid_id_column = [i_grid] * nrows
                        metrics_data['grid index'] = grid_id_column

                        if len(gp_acces_by_grid) == 0:
                            gp_acces_by_grid = metrics_data
                        else:
                            gp_acces_by_grid = pd.concat([gp_acces_by_grid, metrics_data])

                    gp_acces_by_mode.append(gp_acces_by_grid)

                gp_access[instrument] = gp_acces_by_mode
            
        return OrbitData(spacecraft, time_data, eclipse_data, position_data, isl_data, gs_access, gp_access)
    
    def get_next_agent_access(self, dst, t: SimTime):
        src = self.parent_agent

        if isinstance(src, SpacecraftAgent) and isinstance(dst, SpacecraftAgent):
            isl_data = self.isl_data[dst.unique_id]
            for _, row in isl_data.iterrows():
                t_start = row['start index'] * self.time_step
                t_end = row['end index'] * self.time_step

                if t_start <= t <= t_end:
                    return t_start, t_end
                elif t < t_start:
                    return t_start, t_end
        else:
            raise Exception(f'Access between {type(src)} and {type(dst)} not yet supported.')

    def get_next_isl_access(self, target, t):
        target_id = target.unique_id
        return [-np.Infinity, np.Infinity]

    def get_next_gs_access(self, t):
        return [-np.Infinity, np.Infinity]

    def get_next_gp_access(self, lat, lon, t):
        return [-np.Infinity, np.Infinity]

    def get_next_eclipse(self, t: SimTime):
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
        for _, row in self.eclipse_data.iterrows():
            t_start = row['start index'] * self.time_step
            t_end = row['end index'] * self.time_step
            if t_start <= t < t_end:
                return True
        return False

    def get_position(self, t: SimTime):
        # return self.position[t]
        for _, row in self.position_data.iterrows():
            t_row = row['time index'] * self.time_step
            if t_row <= t:
                x = row['x [km]']
                y = row['y [km]']
                z = row['z [km]']
                return [x, y, z]

        return [-1,-1,-1]

    def get_velocity(self, t: SimTime):
        # return self.velocity[t]
        for _, row in self.position_data.iterrows():
            t_row = row['time index'] * self.time_step
            if t_row <= t:
                x = row['vx [km/s]']
                y = row['vy [km/s]']
                z = row['vz [km/s]']
                return [x, y, z]
        return [-1,-1,-1]