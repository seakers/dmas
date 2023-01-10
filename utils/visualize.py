import json
import os
import webbrowser
import time
import copy
import datetime
import pandas as pd
import numpy as np
import orbitpy
import uuid
from orbitdata import OrbitData

class Visualize():    

    def __init__(self,scenario_dir):
        self.scenario_dir = scenario_dir
        self.click_launch()

    def click_launch(self):
        """ Make CZML file based on the mission executed results and execute the cesium app. """

        czml_template_dir = './czml_templates/'
        
        [epoch, step_size, num_time_indices, czml_pkts] = self.build_czmlpkts_for_mission_background(czml_template_dir)

        # _czml_pkts = self.build_czmlpkts_for_ground_stn_contact_opportunities(czml_template_dir, epoch, step_size, num_time_indices)
        # czml_pkts.extend(_czml_pkts)
       

        # _czml_pkts = self.build_czmlpkts_for_intersat_contact_opportunities(czml_template_dir, epoch, step_size, num_time_indices)
        # czml_pkts.extend(_czml_pkts)  

        # write the CZML data file        
        with open(self.scenario_dir+"dmas_viz.czml", 'w') as f:
            json.dump(czml_pkts, f, indent=4)

        #self.execute_cesium_app()       
        
    def execute_cesium_app(self):      
        # Server already started in the `bin/eosimapp.py` script
        os.chdir(os.path.join(os.path.dirname(__file__), '../../../cesium_app')) # change directory to examples
        webbrowser.open('http://localhost:8080/', new=2) # open webbrowser

    def build_czmlpkts_for_mission_background(self,czml_template_dir):
        """ Make CZML packets corresponding to the mission attributes which are operationally independent such 
            as the mission date, satellite orbits, ground-station positions and coverage grid.
            
            :param czml_template_dir: Directory with the CZML packet json templates.
            :paramtype czml_template_dir: str

            :return: List of the following objects: 
                    
                    * CZML packets corresponding to mission-background information. (List of dictionaries.)
                    * Mission epoch. (:class:`datetime.datetime`)
                    * Propagation (time) step-size in seconds. (float)
                    * umber of time-indices i.e. the number of time-steps over which the mission is simulated. (integer)

            :rtype: list

        """


        
        # # make the ground-station packets
        # with open(czml_template_dir+"ground_station_template.json", 'r') as f:
        #     gndstn_pkt_template = json.load(f)
        
        # ground_station = config.mission.groundStation # list of orbitpy.util.GroundStation objects in the mission
        # if ground_station:
        #     for gndstn in ground_station:
        #         _pkt = copy.deepcopy(gndstn_pkt_template)
        #         _pkt["id"] = gndstn._id
        #         _pkt["name"] = gndstn.name
        #         _pkt["label"]["text"] = gndstn.name
        #         _pkt["position"] = {}
        #         _pkt["position"]["cartographicDegrees"] = [gndstn.longitude, gndstn.latitude, gndstn.altitude*1e3]
        #         czml_pkts.append(_pkt)
        czml_pkts = [] # list of packets
        epoch = None
        z_epoch = None
        end_date = None

                # make the clock packet
        with open(czml_template_dir+"clock_template.json", 'r') as f:
            clk_pkt_template = json.load(f) 
        
        # get the mission epoch in Gregorian UTC
        with open(self.scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict = json.load(scenario_specs)
            data_dir = self.scenario_dir + 'orbit_data/'
            spacecraft_list = mission_dict.get('spacecraft')
            for spacecraft in spacecraft_list:
                name = spacecraft.get('name')
                index = spacecraft_list.index(spacecraft)
                agent_folder = "sat" + str(index) + '/'
                sat_state_fp = data_dir + agent_folder + "state_cartesian.csv"
                # load propagation time data
                time_data =  pd.read_csv(sat_state_fp, nrows=3)
                _, epoc_type, _, epoc_greg = time_data.at[0,time_data.axes[1][0]].split(' ')
                epoc_type = epoc_type[1 : -1]
                epoc = float(epoc_greg)
                _, _, _, _, time_step = time_data.at[1,time_data.axes[1][0]].split(' ')
                time_step = float(time_step)

                time_data = { "epoc": epoc, 
                            "epoc type": epoc_type, 
                            "time step": time_step }
                _d = epoc_greg
                epoch = datetime.datetime(int(_d[0]), int(_d[1]), int(_d[2]), int(_d[3]), int(_d[4]), int(_d[5]))

                duration_s = 1.0* 86400
                end_date = epoch + datetime.timedelta(0,int(duration_s))

        clk_pkt = copy.deepcopy(clk_pkt_template)
        clk_pkt["clock"]["interval"] = "2012-03-15T10:00:00Z/2012-03-16T10:00:00Z"
        clk_pkt["clock"]["currentTime"] = "2012-03-15T10:00:00Z"
        
        czml_pkts.append(clk_pkt)
        # make the satellite packets
        with open(czml_template_dir+"satellite_template.json", 'r') as f:
            sat_pkt_template = json.load(f) 

        time_data = None
        # iterate over list of satellites whose orbit-propagation data is available
        with open(self.scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict = json.load(scenario_specs)
            data_dir = self.scenario_dir + 'orbit_data/'

            data = dict()
            spacecraft_list = mission_dict.get('spacecraft')
            gound_station_list = mission_dict.get('groundStation')

            for spacecraft in spacecraft_list:
                name = spacecraft.get('name')
                index = spacecraft_list.index(spacecraft)
                agent_folder = "sat" + str(index) + '/'
                sat_state_fp = data_dir + agent_folder + "state_cartesian.csv"

                # load position data

                (epoch_JDUT1, step_size, duration) = orbitpy.util.extract_auxillary_info_from_state_file(sat_state_fp)
                sat_state_df = pd.read_csv(sat_state_fp, skiprows = [0,1,2,3]) 
                sat_state_df = sat_state_df[['time index','x [km]','y [km]','z [km]']] # velocity information is not needed
                num_time_indices = len(sat_state_df['time index']) # shall be same for all satellites
                # reformat the data to the one expected by Cesium
                sat_state_df['Time[s]'] = np.array(sat_state_df['time index']) * step_size
                sat_state_df['X[m]'] = np.array(sat_state_df['x [km]']) * 1000
                sat_state_df['Y[m]'] = np.array(sat_state_df['y [km]']) * 1000
                sat_state_df['Z[m]'] = np.array(sat_state_df['z [km]']) * 1000
                sat_state_df = sat_state_df[['Time[s]','X[m]','Y[m]','Z[m]']]

                _sat_pkt = copy.deepcopy(sat_pkt_template)
                _sat_pkt["id"] = name
                _sat_pkt["name"] = _sat_pkt["id"]#"Sat"+_sat_pkt["id"]
                _sat_pkt["label"]["text"] = _sat_pkt["name"]
                _sat_pkt["position"]["epoch"] = "2012-03-15T10:00:00Z"
                _sat_pkt["position"]["cartesian"] = sat_state_df.values.flatten().tolist()

                czml_pkts.append(_sat_pkt)





        # make packets showing the coverage grid
        with open(czml_template_dir+"covgrid_pkt_template.json", 'r') as f:
            covgrid_pkt_template = json.load(f)
        # iterate over list of grids in the mission
        grid_data_compiled = []
        with open(self.scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict = json.load(scenario_specs)
            data_dir = self.scenario_dir + 'orbit_data/'
            
            for grid in mission_dict.get('grid'):
                i_grid = mission_dict.get('grid').index(grid)
                grid_file = data_dir + f'grid{i_grid}.csv'

                grid_data = pd.read_csv(grid_file)
                nrows, _ = grid_data.shape
                grid_data['GP index'] = [i for i in range(nrows)]
                grid_data['grid index'] = [i_grid] * nrows
                grid_data_compiled.append(grid_data)
        for grid in grid_data_compiled:
            # each grid-point in the grid is encoded in a separate packet
            for _, row in grid.iterrows():
                _pkt = copy.deepcopy(covgrid_pkt_template)
                _pkt["id"] = "Gridpoint/"+ str(row['grid index']) + "/"+ str(row['GP index'])
                _pkt["position"] = {}
                _pkt["position"]["cartographicDegrees"] = [row['lon [deg]'], row['lat [deg]'], 0]
                czml_pkts.append(_pkt) 

        return [epoch, step_size, num_time_indices, czml_pkts]

    @staticmethod
    def build_czmlpkts_for_ground_stn_contact_opportunities(czml_template_dir, epoch, step_size, num_time_indices):
        """ Build CZML packets with the ground-station contact information.
        
            :param czml_template_dir: Directory with the CZML packet json templates.
            :paramtype czml_template_dir: str

            :param epoch: Mission epoch
            :paramtype epoch: :class:`datetime.datetime`

            :param step_size: propagation (time) step-size in seconds.
            :paramtype step_size: float

            :param num_time_indices: Number of time-indices i.e. the number of time-steps over which the mission is simulated.
            :paramtype num_time_indices: int

            :return: CZML packets corresponding to ground-station contact opportunites. (List of dictionaries.)
            :rtype: list, dict

        """

        czml_pkts = []
        with open(czml_template_dir+"contacts_template.json", 'r') as f:
            contacts_pkt = json.load(f)
        
        contacts_pkt[0]["id"] = str(uuid.uuid4()) # TODO: Not sure if this parent packet is required
        czml_pkts.append(contacts_pkt[0])

        # iterate over all ground-station contact results
        for info in config.mission.outputInfo:
            if info._type == orbitpy.util.OutputInfoUtility.OutputInfoType.ContactFinderOutputInfo.value: # check if outputInfo corresponds to ContactInfo
                if info.entityAtype == "GroundStation" or info.entityBtype == "GroundStation": # check if contact is that with ground-station
                    
                    gndstn_id = info.entityAId if info.entityAtype == "GroundStation" else info.entityBId
                    sat_id = info.entityAId if info.entityAtype == "Spacecraft" else info.entityBId
                    
                    contact_df = pd.read_csv(info.contactFile, skiprows=[0,1,2])

                    # the contacts in the contactFile correspond to contact-intervals. This must be processed to a format (as required by Cesium) in which 
                    # both the contact and no-contact intervals are available. 
                    contacts = []
                    is_first_contact = True
                    previous_row = False
                    for index, row in contact_df.iterrows():
                        
                        if(is_first_contact):                    
                            if(row['start index']!=0): # interval of no contact during the beginning, add this to the contacts (with boolean = False)
                                time_from = epoch.isoformat() + 'Z'
                                time_to = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                                interval = time_from + "/" + time_to
                                contacts.append({"interval":interval, "boolean":False})                   
                        
                        time_from = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                        time_to = (epoch + datetime.timedelta(0,int(row['end index'] * step_size))).isoformat() + 'Z'
                        interval = time_from + "/" + time_to
                        contacts.append({"interval":interval, "boolean":True})

                        if is_first_contact is False:
                            # attach a period of no-contact between the consecutive contact periods
                            time_from = (epoch + datetime.timedelta(0,int(previous_row['end index'] * step_size))).isoformat() + 'Z'
                            time_to = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                            interval = time_from + "/" + time_to
                            contacts.append({"interval":interval, "boolean":False})

                        previous_row = row
                        is_first_contact = False

                    # check the time towards the end
                    if contacts: # if any contacts exist
                        if(previous_row['end index']!=num_time_indices):
                            # attach a period of no-contact between the previous interval-end and end-of-simulation
                            time_from = (epoch + datetime.timedelta(0,int(previous_row['end index'] * step_size))).isoformat() + 'Z'
                            time_to = (epoch + datetime.timedelta(0,num_time_indices * step_size)).isoformat() + 'Z'
                            interval = time_from + "/" + time_to
                            contacts.append({"interval":interval, "boolean":False})
                    
                    _pkt = copy.deepcopy(contacts_pkt[1])
                    _pkt["id"] = str(sat_id) + "-to-" + str(gndstn_id) 
                    _pkt["name"] = _pkt["id"]
                    _pkt["polyline"]["show"] = contacts if bool(contacts) else False # no contacts throughout the mission case
                    _pkt["polyline"]["positions"]["references"] = [str(sat_id)+"#position",str(gndstn_id)+"#position"]
                    
                    czml_pkts.append(_pkt)

        return czml_pkts

    @staticmethod
    def build_czmlpkts_for_intersat_contact_opportunities(czml_template_dir, epoch, step_size, num_time_indices):
        """ Build CZML packets with the inter-satellite contact information.

            :param czml_template_dir: Directory with the CZML packet json templates.
            :paramtype czml_template_dir: str

            :param epoch: Mission epoch
            :paramtype epoch: :class:`datetime.datetime`

            :param step_size: propagation (time) step-size in seconds.
            :paramtype step_size: float

            :param num_time_indices: Number of time-indices i.e. the number of time-steps over which the mission is simulated.
            :paramtype num_time_indices: int

            :return: CZML packets corresponding to inter-satellite contact opportunites. (List of dictionaries.)
            :rtype: list, dict

        """

        czml_pkts = []
        with open(czml_template_dir+"contacts_template.json", 'r') as f:
            contacts_pkt = json.load(f)
        
        contacts_pkt[0]["id"] = str(uuid.uuid4()) # TODO: Not sure if this parent packet is required
        czml_pkts.append(contacts_pkt[0])

        # iterate over all inter-satellite contact results
        for info in config.mission.outputInfo:
            if info._type == orbitpy.util.OutputInfoUtility.OutputInfoType.ContactFinderOutputInfo.value: # check if outputInfo corresponds to ContactInfo
                if info.entityAtype == "Spacecraft" or info.entityBtype == "GroundStation": # check if contact is that between satellites
                    
                    satA_id = info.entityAId
                    satB_id = info.entityBId
                    
                    contact_df = pd.read_csv(info.contactFile, skiprows=[0,1,2])

                    # the contacts in the contactFile correspond to contact-intervals. This must be processed to a format (as required by Cesium) in which 
                    # both the contact and no-contact intervals are available. 
                    contacts = []
                    is_first_contact = True
                    previous_row = False
                    for index, row in contact_df.iterrows():
                        
                        if(is_first_contact):                    
                            if(row['start index']!=0): # interval of no contact during the beginning, add this to the contacts (with boolean = False)
                                time_from = epoch.isoformat() + 'Z'
                                time_to = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                                interval = time_from + "/" + time_to
                                contacts.append({"interval":interval, "boolean":False})                   
                        
                        time_from = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                        time_to = (epoch + datetime.timedelta(0,int(row['end index'] * step_size))).isoformat() + 'Z'
                        interval = time_from + "/" + time_to
                        contacts.append({"interval":interval, "boolean":True})

                        if is_first_contact is False:
                            # attach a period of no-contact between the consecutive contact periods
                            time_from = (epoch + datetime.timedelta(0,int(previous_row['end index'] * step_size))).isoformat() + 'Z'
                            time_to = (epoch + datetime.timedelta(0,int(row['start index'] * step_size))).isoformat() + 'Z'
                            interval = time_from + "/" + time_to
                            contacts.append({"interval":interval, "boolean":False})

                        previous_row = row
                        is_first_contact = False

                    # check the time towards the end
                    if contacts: # if any contacts exist
                        if(previous_row['end index']!=num_time_indices):
                            # attach a period of no-contact between the previous interval-end and end-of-simulation
                            time_from = (epoch + datetime.timedelta(0,int(previous_row['end index'] * step_size))).isoformat() + 'Z'
                            time_to = (epoch + datetime.timedelta(0,num_time_indices * step_size)).isoformat() + 'Z'
                            interval = time_from + "/" + time_to
                            contacts.append({"interval":interval, "boolean":False})
                    
                    _pkt = copy.deepcopy(contacts_pkt[1])
                    _pkt["id"] = str(satA_id) + "-to-" + str(satB_id) 
                    _pkt["name"] = _pkt["id"]
                    _pkt["polyline"]["show"] = contacts if bool(contacts) else False # no contacts throughout the mission case
                    _pkt["polyline"]["positions"]["references"] = [str(satA_id)+"#position",str(satB_id)+"#position"]
                    
                    czml_pkts.append(_pkt)

        return czml_pkts

    
if __name__ == '__main__':
    scenario_dir = './scenarios/scenario1_agile/'
    Visualize(scenario_dir)
        