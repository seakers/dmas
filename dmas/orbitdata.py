import json
import os
import re
from orbitpy.mission import Mission
import pandas as pd
import numpy as np

class TimeInterval:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        if self.end < self.start:
            raise Exception('The end of time interval must be later than beginning of the interval.')

    def is_after(self, t):
        return t < self.start

    def is_before(self, t):
        return self.end < t

    def is_during(self, t):
        return self.start <= t <= self.end


class OrbitData:
    """
    Stores and queries data regarding an agent's orbital data. 

    TODO: add support to load ground station agents' data
    """
    def __init__(self, agent_name: str, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data):
        # name of agent being represented by this object
        self.agent_name = agent_name

        # propagation time specifications
        self.time_step = time_data['time step']
        self.epoc_type = time_data['epoc type']
        self.epoc = time_data['epoc']

        # agent position and eclipse information
        self.eclipse_data = eclipse_data.sort_values(by=['start index'])
        self.position_data = position_data.sort_values(by=['time index'])

        # inter-satellite communication access times
        self.isl_data = {}
        for satellite_name in isl_data.keys():
            self.isl_data[satellite_name] = isl_data[satellite_name].sort_values(by=['start index'])

        # ground station access times
        self.gs_access_data = gs_access_data.sort_values(by=['start index'])
        
        # ground point access times
        self.gp_access_data = gp_access_data.sort_values(by=['time index'])
    
    def get_next_agent_access(self, target, t: float):
        src = self.agent_name

        if target in self.isl_data.keys():
            return self.get_next_isl_access_interval(target, t)
        else:
            raise Exception(f'Access between {src} and {target} not supported.')

    def get_next_isl_access_interval(self, target, t) -> TimeInterval:
        isl_data = self.isl_data[target]
        
        for _, row in isl_data.iterrows():
            t_start = row['start index'] * self.time_step
            t_end = row['end index'] * self.time_step

            interval = TimeInterval(t_start, t_end)
            if interval.is_during(t) or interval.is_after(t):
                return interval

        return TimeInterval(-np.Infinity, np.Infinity)

    def get_next_gs_access_interval(self, t):
        return [-np.Infinity, np.Infinity]

    def get_next_gp_access_interval(self, lat: float, lon: float, t: float):
        """
        Returns the next access to a ground point
        """
        # find closest gridpoint 
        grid_index, gp_index = self.find_gp_index(lat,lon)

        # find next access

        interval = TimeInterval(-np.Infinity, np.Infinity)
        instruments = []
        modes = dict()
        return interval, instruments, modes

    def find_gp_index(self, lat: float, lon: float):
        """
        Returns the ground point and grid index to the point closest to the latitude and longitude given.

        lat, lon must be given in degrees
        """
        return -1, -1

    def get_next_eclipse_interval(self, t: float):
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

    def is_eclipse(self, t: float):
        for _, row in self.eclipse_data.iterrows():
            t_start = row['start index'] * self.time_step
            t_end = row['end index'] * self.time_step

            interval = TimeInterval(t_start, t_end)
            if interval.is_during(t):
                return True
        return False

    def get_position(self, t: float):
        for _, row in self.position_data.iterrows():
            t_row = row['time index'] * self.time_step
            if t_row <= t:
                x = row['x [km]']
                y = row['y [km]']
                z = row['z [km]']
                return [x, y, z]

        return [-1,-1,-1]

    def get_velocity(self, t: float):
        for _, row in self.position_data.iterrows():
            t_row = row['time index'] * self.time_step
            if t_row <= t:
                x = row['vx [km/s]']
                y = row['vy [km/s]']
                z = row['vz [km/s]']
                return [x, y, z]
        return [-1,-1,-1]

    def get_orbit_state(self, t: float):
        for _, row in self.position_data.iterrows():
            t_row = row['time index'] * self.time_step
            if t_row <= t:
                x = row['x [km]']
                y = row['y [km]']
                z = row['z [km]']
                vx = row['vx [km/s]']
                vy = row['vy [km/s]']
                vz = row['vz [km/s]']
                return [x, y, z, vx, vy, vz]
        return [-1,-1,-1]

    def from_directory(scenario_dir: str):
        """
        Loads orbit data from a directory containig a json file specifying the details of the mission being simulated.
        If the data has not been previously propagated, it will do so and store it in the same directory as the json file
        being used.

        The data gets stored as a dictionary, with each entry containing the orbit data of each agent in the mission 
        indexed by the name of the agent.
        """
        print('Loading orbit and coverage data...')
        data_dir = scenario_dir + 'orbit_data/'

        changes_to_scenario = False
        with open(scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # check if data has been previously calculated
            if os.path.exists(data_dir + 'MissionSpecs.json'):
                with open(data_dir +'MissionSpecs.json', 'r') as mission_specs:
                    scenario_dict = json.load(scenario_specs)
                    mission_dict = json.load(mission_specs)
                    if scenario_dict != mission_dict:
                        changes_to_scenario = True
            else:
                changes_to_scenario = True
        
        if not os.path.exists(data_dir):
            # if directory does not exists, create it
            os.mkdir(data_dir)
            changes_to_scenario = True

        if not changes_to_scenario:
            # if propagation data files already exist, load results
            print('Orbit data found!')
        else:
            # if propagation data files do not exist, propagate and then load results
            if changes_to_scenario:
                print('Existing orbit data does not match scenario.')
            else:
                print('Orbit data not found.')

            print('Clearing \'orbit_data\' directory...')    
            # clear files if they exist
            if os.path.exists(data_dir):
                for f in os.listdir(data_dir):
                    if os.path.isdir(os.path.join(data_dir, f)):
                        for h in os.listdir(data_dir + f):
                             os.remove(os.path.join(data_dir, f, h))
                        os.rmdir(data_dir + f)
                    else:
                        os.remove(os.path.join(data_dir, f)) 
            print('\'orbit_data\' cleared!')

            with open(scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
                # load json file as dictionary
                mission_dict = json.load(scenario_specs)

                # save specifications of propagation in the orbit data directory
                with open(data_dir +'MissionSpecs.json', 'w') as mission_specs:
                    mission_specs.write(json.dumps(mission_dict, indent=4))

                # set output directory to orbit data directory
                if mission_dict.get("settings", None) is not None:
                    mission_dict["settings"]["outDir"] = scenario_dir + '/orbit_data/'
                else:
                    mission_dict["settings"] = {}
                    mission_dict["settings"]["outDir"] = scenario_dir + '/orbit_data/'

                # propagate data and save to orbit data directory
                print("Propagating orbits...")
                mission = Mission.from_json(mission_dict)  
                mission.execute()                
                print("Propagation done!")

        print('Loading orbit data...')
        with open(scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict = json.load(scenario_specs)

            data = dict()
            spacecraft_list = mission_dict.get('spacecraft')
            gound_station_list = mission_dict.get('groundStation')

            for spacecraft in spacecraft_list:
                name = spacecraft.get('name')
                index = spacecraft_list.index(spacecraft)
                agent_folder = "sat" + str(index) + '/'

                # load eclipse data
                eclipse_file = data_dir + agent_folder + "eclipses.csv"
                eclipse_data = pd.read_csv(eclipse_file, skiprows=range(3))
                
                # load position data
                position_file = data_dir + agent_folder + "state_cartesian.csv"
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
                for file in os.listdir(data_dir + '/comm/'):                
                    isl = re.sub(".csv", "", file)
                    sender, _, receiver = isl.split('_')

                    if 'sat' + str(index) in sender or 'sat' + str(index) in receiver:
                        isl_file = data_dir + 'comm/' + file
                        if 'sat' + str(index) in sender:
                            receiver_index = int(re.sub("[^0-9]", "", receiver))
                            receiver_name = spacecraft_list[receiver_index].get('name')
                            isl_data[receiver_name] = pd.read_csv(isl_file, skiprows=range(3))
                        else:
                            sender_index = int(re.sub("[^0-9]", "", sender))
                            sender_name = spacecraft_list[sender_index].get('name')
                            isl_data[sender_name] = pd.read_csv(isl_file, skiprows=range(3))

                # load ground station access data
                gs_access_data = pd.DataFrame(columns=['start index', 'end index', 'gndStn id', 'gndStn name','lat [deg]','lon [deg]'])
                for file in os.listdir(data_dir + agent_folder):
                    if 'gndStn' in file:
                        gndStn_access_file = data_dir + agent_folder + file
                        gndStn_access_data = pd.read_csv(gndStn_access_file, skiprows=range(3))
                        nrows, _ = gndStn_access_data.shape

                        if nrows > 0:
                            gndStn, _ = file.split('_')
                            gndStn_index = int(re.sub("[^0-9]", "", gndStn))
                            
                            gndStn_name = gound_station_list[gndStn_index].get('name')
                            gndStn_id = gound_station_list[gndStn_index].get('@id')
                            gndStn_lat = gound_station_list[gndStn_index].get('latitude')
                            gndStn_lon = gound_station_list[gndStn_index].get('longitude')

                            gndStn_name_column = [gndStn_name] * nrows
                            gndStn_id_column = [gndStn_id] * nrows
                            gndStn_lat_column = [gndStn_lat] * nrows
                            gndStn_lon_column = [gndStn_lon] * nrows

                            gndStn_access_data['gndStn name'] = gndStn_name_column
                            gndStn_access_data['gndStn id'] = gndStn_id_column
                            gndStn_access_data['lat [deg]'] = gndStn_lat_column
                            gndStn_access_data['lon [deg]'] = gndStn_lon_column

                            if len(gs_access_data) == 0:
                                gs_access_data = gndStn_access_data
                            else:
                                gs_access_data = pd.concat([gs_access_data, gndStn_access_data])

                # land coverage data metrics data
                payload = spacecraft.get('instrument', None)
                if not isinstance(payload, list):
                    payload = [payload]

                gp_access_data = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]', 'agent','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                for instrument in payload:
                    i_ins = payload.index(instrument)
                    gp_acces_by_mode = []

                    modes = spacecraft.get('instrument', None)
                    if not isinstance(modes, list):
                        modes = [0]

                    gp_acces_by_mode = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]','instrument',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])
                    for mode in modes:
                        i_mode = modes.index(mode)
                        gp_access_by_grid = pd.DataFrame(columns=['time index','GP index','pnt-opt index','lat [deg]','lon [deg]',
                                                                'observation range [km]','look angle [deg]','incidence angle [deg]','solar zenith [deg]'])

                        for grid in mission_dict.get('grid'):
                            i_grid = mission_dict.get('grid').index(grid)
                            metrics_file = data_dir + agent_folder + f'datametrics_instru{i_ins}_mode{i_mode}_grid{i_grid}.csv'
                            metrics_data = pd.read_csv(metrics_file, skiprows=range(4))
                            
                            nrows, _ = metrics_data.shape
                            grid_id_column = [i_grid] * nrows
                            metrics_data['grid index'] = grid_id_column

                            if len(gp_access_by_grid) == 0:
                                gp_access_by_grid = metrics_data
                            else:
                                gp_access_by_grid = pd.concat([gp_access_by_grid, metrics_data])

                        nrows, _ = gp_access_by_grid.shape
                        gp_access_by_grid['pnt-opt index'] = [mode] * nrows

                        if len(gp_acces_by_mode) == 0:
                            gp_acces_by_mode = gp_access_by_grid
                        else:
                            gp_acces_by_mode = pd.concat([gp_acces_by_mode, gp_access_by_grid])
                        # gp_acces_by_mode.append(gp_access_by_grid)

                    nrows, _ = gp_acces_by_mode.shape
                    gp_access_by_grid['instrument'] = [instrument] * nrows
                    # gp_access_data[ins_name] = gp_acces_by_mode

                    if len(gp_access_data) == 0:
                        gp_access_data = gp_acces_by_mode
                    else:
                        gp_access_data = pd.concat([gp_access_data, gp_acces_by_mode])
                
                nrows, _ = gp_access_data.shape
                gp_access_data['agent'] = [spacecraft] * nrows

                data[name] = OrbitData(name, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data)

            return data