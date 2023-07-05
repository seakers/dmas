import asyncio
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
    def __init__(self, agent_name : str, 
                    time_data : pd.DataFrame, 
                    eclipse_data : pd.DataFrame, 
                    position_data : pd.DataFrame, 
                    isl_data : pd.DataFrame,
                    gs_access_data : pd.DataFrame, 
                    gp_access_data : pd.DataFrame, 
                    grid_data : pd.DataFrame):
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

        # grid indofmation
        self.grid_data = grid_data
    
    """
    GET NEXT methods
    """
    def get_next_agent_access(self, target, t: float):
        src = self.agent_name

        if target in self.isl_data.keys():
            return self.get_next_isl_access_interval(target, t)
        else:
            raise Exception(f'Access between {src} and {target} not supported.')

    def get_next_isl_access_interval(self, target, t) -> TimeInterval:
        isl_data : pd.DataFrame = self.isl_data[target]
        
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
        grid_index, gp_index, _, _ = self.find_gp_index(lat, lon)

        # find next access
        interval = TimeInterval(-np.Infinity, np.Infinity)
        instruments = []
        modes = dict()
        return interval, instruments, modes

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

    """
    STATE QUERY methods
    """
    def is_accessing_agent(self, target: str, t: float) -> bool:
        if target in self.agent_name:
            return True

        if target not in self.isl_data.keys():
            return False 

        t = t/self.time_step
        nrows, _ = self.isl_data[target].query('`start index` <= @t & @t <= `end index`').shape
               
        return bool(nrows > 0)

    def is_accessing_ground_station(self, target : str, t: float) -> bool:
        t = t/self.time_step
        nrows, _ = self.gs_access_data.query('`start index` <= @t & @t <= `end index` & `gndStn name` == @target').shape
        return bool(nrows > 0)

    def is_accessing_ground_point(self, lat: float, lon: float, t: float):
        t = t/self.time_step
        t_u = t + 1
        t_l = t - 1

        grid_index, gp_index, _, _ = self.find_gp_index(lat, lon)

        access_data = self.gp_access_data \
                            .query('@t_l < `time index` < @t_u & `grid index` == @grid_index & `GP index` == @gp_index') \
                            .sort_values(by=['time index'])

        nrows, _ = access_data.shape

        if nrows == 0:
            return False
        elif nrows == 1:
            for _, row in access_data.iterrows():
                return bool(np.absolute(row['time index'] - t) <= 1e-6)
        else:
            return True            

    def is_eclipse(self, t: float):
        t = t/self.time_step
        nrows, _ = self.eclipse_data.query('`start index` <= @t & @t <= `end index`').shape

        return bool(nrows > 0)

    def get_position(self, t: float):
        pos, _, _ = self.get_orbit_state(t)
        return pos

    def get_velocity(self, t: float):
        _, vel, _ = self.get_orbit_state(t)
        return vel
        
    def get_orbit_state(self, t: float):
        is_eclipse = self.is_eclipse(t)

        t_u = t + self.time_step
        t_l = t - self.time_step

        t = t/self.time_step
        t_u = t_u/self.time_step
        t_l = t_l/self.time_step

        data = self.position_data.query('@t_l < `time index` < @t_u')

        dt_min = None
        touple_min = None
        for _, row in data.iterrows():
            t_row = row['time index']
            dt = np.abs(t_row - t)

            x = row['x [km]']
            y = row['y [km]']
            z = row['z [km]']
            pos = [x, y, z]

            vx = row['vx [km/s]']
            vy = row['vy [km/s]']
            vz = row['vz [km/s]']
            vel = [vx, vy, vz]
            
            if dt_min is None or dt < dt_min:
                touple_min = (pos, vel, is_eclipse)
                dt_min = dt            
        
        if touple_min is None:
            return (None, None, None)
        else:
            return touple_min

    def get_ground_point_accesses_future(self, lat: float, lon: float, t: float):
        t = t/self.time_step

        grid_index, gp_index, _, _ = self.find_gp_index(lat, lon)

        access_data = self.gp_access_data \
                            .query('@t <= `time index` & `grid index` == @grid_index & `GP index` == @gp_index') \
                            .sort_values(by=['time index'])

        return access_data
    
    def find_gp_index(self, lat: float, lon: float) -> tuple:
        """
        Returns the ground point and grid index to the point closest to the latitude and longitude given.

        lat, lon must be given in degrees
        """
        grid_compiled = None
        for grid in self.grid_data:
            
            if grid_compiled is None:
                grid_compiled = grid
            else:
                grid_compiled = pd.concat([grid_compiled, grid])
        
        perfect_match = grid_compiled.query('`lat [deg]` == @lat & `lon [deg]` == @lon')

        for _, row in perfect_match.iterrows():
            grid_index = row['grid index']
            gp_index = row['GP index']
            gp_lat = row['lat [deg]']
            gp_lon = row['lon [deg]']

            return grid_index, gp_index, gp_lat, gp_lon
            
        grid_compiled['dr'] = np.sqrt( 
                                        np.power(np.cos( grid_compiled['lat [deg]'] * np.pi / 360 ) * np.cos( grid_compiled['lon [deg]'] * np.pi / 360 ) \
                                                - np.cos( lat * np.pi / 360 ) * np.cos( lon * np.pi / 360 ), 2) \
                                        + np.power(np.cos( grid_compiled['lat [deg]'] * np.pi / 360 ) * np.sin( grid_compiled['lon [deg]'] * np.pi / 360 ) \
                                                - np.cos( lat * np.pi / 360 ) * np.sin( lon * np.pi / 360 ), 2) \
                                        + np.power(np.sin( grid_compiled['lat [deg]'] * np.pi / 360 ) \
                                                - np.sin( lat * np.pi / 360 ), 2)
                                    )
        min_dist = grid_compiled['dr'].min()
        min_rows = grid_compiled.query('dr == @min_dist')

        for _, row in min_rows.iterrows():
            grid_index = row['grid index']
            gp_index = row['GP index']
            gp_lat = row['lat [deg]']
            gp_lon = row['lon [deg]']

            return grid_index, gp_index, gp_lat, gp_lon

        return -1, -1, -1, -1

    def from_directory(scenario_dir: str) -> dict:
        """
        Loads orbit data from a directory containig a json file specifying the details of the mission being simulated.
        If the data has not been previously propagated, it will do so and store it in the same directory as the json file
        being used.

        The data gets stored as a dictionary, with each entry containing the orbit data of each agent in the mission 
        indexed by the name of the agent.
        """
        data_dir = scenario_dir + '/orbitdata/'
        with open(scenario_dir + '/MissionSpecs.json', 'r') as scenario_specs:
            
            # load json file as dictionary
            mission_dict : dict = json.load(scenario_specs)
            data = dict()
            spacecraft_list : list = mission_dict.get('spacecraft', None)
            uav_list : list = mission_dict.get('uav', None)
            ground_station_list = mission_dict.get('groundStation', None)

            # load pre-computed data
            if spacecraft_list:
                for spacecraft in spacecraft_list:
                    spacecraft : dict
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
                                
                                gndStn_name = ground_station_list[gndStn_index].get('name')
                                gndStn_id = ground_station_list[gndStn_index].get('@id')
                                gndStn_lat = ground_station_list[gndStn_index].get('latitude')
                                gndStn_lon = ground_station_list[gndStn_index].get('longitude')

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

                        # modes = spacecraft.get('instrument', None)
                        # if not isinstance(modes, list):
                        #     modes = [0]
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
                    gp_access_data['agent name'] = [spacecraft['name']] * nrows

                    grid_data_compiled = []
                    for grid in mission_dict.get('grid'):
                        i_grid = mission_dict.get('grid').index(grid)
                        grid_file = data_dir + f'grid{i_grid}.csv'

                        grid_data = pd.read_csv(grid_file)
                        nrows, _ = grid_data.shape
                        grid_data['GP index'] = [i for i in range(nrows)]
                        grid_data['grid index'] = [i_grid] * nrows
                        grid_data_compiled.append(grid_data)

                    data[name] = OrbitData(name, time_data, eclipse_data, position_data, isl_data, gs_access_data, gp_access_data, grid_data_compiled)

            if ground_station_list:
                for groundstation in ground_station_list:
                    pass

            return data

"""
TESTING
"""
async def main(scenario_dir):
    orbit_data_list = OrbitData.from_directory(scenario_dir)

    # expected val: (grid, point) = 0, 0
    for agent in orbit_data_list:
        lat = 1.0
        lon = 158.0
        t = 210.5

        grid, point, gp_lat, gp_lon = orbit_data_list[agent].find_gp_index(lat, lon)
        print(f'({lat}, {lon}) = G{grid}, P{point}, Lat{gp_lat}, Lon{gp_lon}')

        print(orbit_data_list[agent].is_accessing_ground_point(lat, lon, t))
        break


if __name__ == '__main__':
    scenario_dir = './scenarios/sim_test/'
    asyncio.run(main(scenario_dir))