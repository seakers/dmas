import csv
import numpy as np
import pandas as pd
import datetime as dt
from nodes.actions import MeasurementAction
from nodes.states import SimulationAgentState
from messages import *
from nodes.science.reqs import *
from zmq import asyncio as azmq
from dmas.modules import *


class ScienceModuleTypes(Enum):
    SCENARIO1 = 'SCENARIO1' 
    SCENARIO2 = 'SCENARIO2'


class ScienceModule(InternalModule):
    def __init__(   self, 
                    results_path : str,
                    scenario_path : str,
                    parent_name : str,
                    parent_network_config: NetworkConfig, 
                    logger: logging.Logger = None
                ) -> None:

        addresses = parent_network_config.get_internal_addresses()        
        sub_addesses = []
        sub_address : str = addresses.get(zmq.PUB)[0]
        sub_addesses.append( sub_address.replace('*', 'localhost') )
        sub_address : str = addresses.get(zmq.SUB)[0]
        sub_addesses.append( sub_address.replace('*', 'localhost') )

        pub_address : str = addresses.get(zmq.SUB)[1]
        pub_address = pub_address.replace('localhost', '*')

        addresses = parent_network_config.get_manager_addresses()
        push_address : str = addresses.get(zmq.PUSH)[0]

        science_network_config =  NetworkConfig(parent_name,
                                        manager_address_map = {
                                        zmq.REQ: [],
                                        zmq.SUB: sub_addesses,
                                        zmq.PUB: [pub_address],
                                        zmq.PUSH: [push_address]})

        super().__init__(   f"{parent_name}-SCIENCE_MODULE", 
                            science_network_config, 
                            parent_network_config, 
                            logging.INFO, 
                            logger)
        
        self.results_path = results_path
        self.scenario_dir = scenario_path
        self.parent_name = parent_name
    
    async def sim_wait(self, delay: float) -> None:
        return

    async def setup(self) -> None:
        # setup internal inboxes
        self.science_value_inbox = asyncio.Queue()
        self.science_reasoning_inbox = asyncio.Queue()
        self.onboard_processing_inbox = asyncio.Queue()
        self.processed_items = []
        self.sd = []
        if "scenario1a" in self.scenario_dir:
            self.points = self.load_points_scenario1a()
            self.log(f'Scenario 1a points loaded!',level=logging.INFO)
        elif "scenario1b" in self.scenario_dir:
            self.points = self.load_points_scenario1b()
            self.log(f'Scenario 1b points loaded!',level=logging.INFO)
        elif "scenario2" in self.scenario_dir:
            self.points = self.load_events_scenario2()
            self.log(f'Scenario 2 points loaded!',level=logging.INFO)
    
    def load_points_scenario1a(self):
        points = np.zeros(shape=(1000,4))
        with open(self.scenario_dir+'resources/riverATLAS.csv') as csvfile:
            reader = csv.reader(csvfile)
            count = 0
            for row in reader:
                if count == 0:
                    count = 1
                    continue
                points[count-1,:] = [row[0], row[1], row[2], row[3]]
                count = count + 1
        return points

    def load_points_scenario1b(self):
        points = []
        with open(self.scenario_dir+'resources/one_year_floods_multiday.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                if len(points) > 0:
                    points.append((line["lat"],line["lon"],line["severity"],line["time"],float(line["time"])+60*60,1))
                else:
                    points.append((line["lat"],line["lon"],line["severity"],line["time"],float(line["time"])+60*60,1))
        with open(self.scenario_dir+'resources/flow_events_75_multiday.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                if len(points) > 0:
                    points.append((line["lat"],line["lon"],float(line["water_level"])/float(line["flood_level"]),line["time"],float(line["time"])+86400,0))
                else:
                    points.append((line["lat"],line["lon"],float(line["water_level"])/float(line["flood_level"]),line["time"],float(line["time"])+86400,0))
        points = np.asfarray(points)
        self.log(f'Loaded scenario 1b points',level=logging.INFO)
        return points

    def load_events_scenario2(self):
        points = []
        # 0 is height, 1 is temperature
        with open(self.scenario_dir+'resources/grealm.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat"],line["lon"],line["avg"],line["std"],line["date"],line["value"],0))
        with open(self.scenario_dir+'resources/laketemps.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat"],line["lon"],line["avg"],line["std"],line["date"],line["value"],1))
        with open(self.scenario_dir+'resources/blooms.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat"],line["lon"],line["avg"],line["std"],line["date"],line["value"],2))
        with open(self.scenario_dir+'resources/extralakes.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat"],line["lon"],0.0,1000000.0,"20220601",0.0,0))
                points.append((line["lat"],line["lon"],0.0,1000000.0,"20220601",0.0,1))
                points.append((line["lat"],line["lon"],0.0,1000000.0,"20220601",0.0,2))
        points = np.asfarray(points)
        self.log(f'Loaded scenario 2 points',level=logging.INFO)
        return points

    def load_events_scenario2_revised(self): # revised 9/1/23
        points = []
        # 0 is bloom, 1 is temperature
        with open(self.scenario_dir+'resources/bloom_events.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat [deg]"],line["lon [deg]"],line["start time [s]"],line["duration [s]"],line["severity"],0))
        with open(self.scenario_dir+'resources/temperature_events.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat [deg]"],line["lon [deg]"],line["start time [s]"],line["duration [s]"],line["severity"],1))
        with open(self.scenario_dir+'resources/level_events.csv', 'r') as f:
            d_reader = csv.DictReader(f)
            for line in d_reader:
                points.append((line["lat [deg]"],line["lon [deg]"],line["start time [s]"],line["duration [s]"],line["severity"],2))
        points = np.asfarray(points)
        self.log(f'Loaded scenario 2 points',level=logging.INFO)
        return points
        
    async def live(self) -> None:
        """
        Performs concurrent tasks:
        - Listener: receives messages from the parent agent and checks results
        - Science valuer: determines value of a given measurement
        - Science reasoning: checks data for outliers
        - Onboard processing: converts data of one type into data of another type (e.g. level 0 to level 1)
        """
        listener_task = asyncio.create_task(self.listener(), name='listener()')
        science_value_task = asyncio.create_task(self.science_value(), name='science_value()')
        #science_reasoning_task = asyncio.create_task(self.science_reasoning(), name='science_reasoning()')
        onboard_processing_task = asyncio.create_task(self.onboard_processing(), name='onboard_processing()')
        
        # , science_value_task, science_reasoning_task, onboard_processing_task
        tasks = [listener_task,science_value_task,onboard_processing_task]
        
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task : asyncio.Task
            task.cancel()
            await task

    async def listener(self):
        """
        ## Listener 

        Listen for any messages from the parent agent and adjust its results ledger.
        Any relevant bids that may affect the bundle, along with any changes in state or 
        task completion status are forwarded to the bundle builder.
        """
        # 
        try:
            # initiate results tracker
            results = {}

            # create poller for all broadcast sockets
            poller = azmq.Poller()
            manager_socket, _ = self._manager_socket_map.get(zmq.SUB)
            poller.register(manager_socket, zmq.POLLIN)

            # listen for broadcasts and place in the appropriate inboxes
            while True:
                self.log('listening to manager broadcast!')
                _, _, content = await self.listen_manager_broadcast()
                if content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    self.log(f"received senses from parent agent!", level=logging.DEBUG)

                    # unpack message 
                    senses_msg : SensesMessage = SensesMessage(**content)

                    senses = []
                    senses.append(senses_msg.state)
                    senses.extend(senses_msg.senses)     

                    for sense in senses:
                        if sense['msg_type'] == SimulationMessageTypes.MEASUREMENT.value:
                            # unpack message
                            if('agent_state' not in sense):
                                continue
                            self.log(f"received manager broadcast of type {sense['msg_type']}!",level=logging.DEBUG)
                            msg = MeasurementResultsRequestMessage(**sense)
                            await self.science_value_inbox.put(msg)
                            await self.onboard_processing_inbox.put(msg)

                # if sim-end message, end agent `live()`
                if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                    self.log(f"received manager broadcast of type {content['msg_type']}! terminating `live()`...",level=logging.INFO)
                    return

                if content['msg_type'] == SimulationMessageTypes.MEASUREMENT.value:
                    # unpack message
                    self.log(f"received manager broadcast of type {content['msg_type']}!",level=logging.WARN)
                    msg = MeasurementResultsRequestMessage(**content)
                    await self.science_value_inbox.put(msg)

                    # elif content['msg_type'] == SimulationMessageTypes.SENSES.value:
                    #     # unpack message
                    #     msg : SensesMessage = SensesMessage(**content)

                    #     self.log('Received agent state in science module!',level=logging.WARN)
                    #     await self.science_value_inbox.put(msg)

                    # elif content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                    #     # unpack message 
                    #     msg : AgentStateMessage = AgentStateMessage(**content)
                        
                    #     # send to bundle builder 
                    #     self.log('Received agent state in science module!',level=logging.WARN)
                    #     await self.science_value_inbox.put(msg)

                    # else, ignore it
        
        except asyncio.CancelledError:
            print("Asyncio cancelled error in science module listener")
            return
        
    async def science_value(self):
        try:
            while True:
                msg : MeasurementResultsRequestMessage = await self.science_value_inbox.get()
                self.log(f'Got message in science_value!',level=logging.INFO)
                
                # print(msg)
                measurement_action = MeasurementAction(**msg.measurement_action)
                agent_state = SimulationAgentState.from_dict(msg.agent_state)
                measurement_req = MeasurementRequest.from_dict(measurement_action.measurement_req)
                obs = {}
                if(measurement_action.instrument_name == "Imaging SAR"):
                    obs["product_type"] = "sar"
                elif(measurement_action.instrument_name == "OLI"):
                    obs["product_type"] = "visible"
                else:
                    obs["product_type"] = "thermal"
                obs["lat"] = measurement_req.lat_lon_pos[0]
                obs["lon"] = measurement_req.lat_lon_pos[1]

                if isinstance(measurement_req, GroundPointMeasurementRequest):
                    lat, lon, _ = measurement_req.lat_lon_pos
                    
                    science_value, outlier_data = self.compute_science_value(lat, lon, obs)
                    self.log('Computed the science value!',level=logging.INFO)
                    metadata = {
                        "observation" : obs
                    }
                    desired_variables = []

                    # if "scenario1a" in self.scenario_dir:
                    #     desired_variables = ["visible"]
                    # elif "scenario1b" in self.scenario_dir:
                    #     desired_variables = ["visible","altimetry"]
                    if "scenario2" in self.scenario_dir:
                        if outlier_data["event_type"] == "bloom":
                            desired_variables = ["visible","sar","thermal"]
                        if outlier_data["event_type"] == "temp":
                            desired_variables = ["visible","thermal"]
                        if outlier_data["event_type"] == "level":
                            desired_variables = ["visible","sar"]
                    # else:
                    #     self.log(f'Scenario not supported by request_handler',level=logging.INFO)

                    # TODO for Alan: hook this up to the planner?
                    measurement_request = MeasurementRequest(desired_variables, lat, lon, science_value, metadata)

                    req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
                    ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, measurement_request)
                    if self.parent_module.notifier == "True":
                        await self.send_internal_message(req_msg)
                        await self.send_internal_message(ext_msg)
                        self.log(f'Sent message to transmitter!',level=logging.DEBUG)

                else:
                    # ignore
                    continue
                
        except Exception as e:
            raise e

        except asyncio.CancelledError:
            return
        
    async def science_reasoning(self):
        try:
            while True:
                msg = await self.science_reasoning_inbox.get()
                outliers = []
                for item in self.sd:
                    if(item["product_type"] == "visible"):
                        if item["checked"] is False:
                            if "scenario2" in self.scenario_dir:
                                level_outlier, level_outlier_data = self.check_lakelevel_outliers(item)
                                temp_outlier, temp_outlier_data = self.check_laketemp_outliers(item)
                                bloom_outlier, bloom_outlier_data = self.check_bloom_outliers(item)
                            if level_outlier is True:
                                self.log(f'Visible outlier in check_sd',level=logging.DEBUG)
                                outliers.append(level_outlier_data)
                            if temp_outlier is True:
                                self.log(f'Visible outlier in check_sd',level=logging.DEBUG)
                                outliers.append(temp_outlier_data)
                            if bloom_outlier is True:
                                self.log(f'Visible outlier in check_sd',level=logging.DEBUG)
                                outliers.append(bloom_outlier_data)

                    elif(item["product_type"] == "sar"):
                        if item["checked"] is False:
                            if "scenario1a" in self.scenario_dir:
                                outlier, outlier_data = self.check_altimetry_outlier(item)
                            if "scenario1b" in self.scenario_dir:
                                outlier, outlier_data = self.check_flood_outliers(item) # TODO implement method
                            if "scenario2" in self.scenario_dir:
                                outlier, outlier_data = self.check_lakelevel_outliers(item)
                            if outlier is True:
                                self.log(f'SAR outlier in check_sd',level=logging.DEBUG)
                                outliers.append(outlier_data)
                            item["checked"] = True

                    elif(item["product_type"] == "thermal"):
                        if item["checked"] is False:
                            if "scenario2" in self.scenario_dir:
                                outlier, outlier_data = self.check_laketemp_outliers(item)
                            if outlier is True:
                                self.log(f'Thermal outlier in check_sd',level=logging.INFO)
                                outliers.append(outlier_data)
                            item["checked"] = True 

                    else:
                        self.log(f'Item in science database unsupported by science processing module.',level=logging.DEBUG)
        except asyncio.CancelledError:
            return
        
    async def onboard_processing(self):
        try:
            while True:
                msg : MeasurementResultsRequestMessage = await self.onboard_processing_inbox.get()
                measurement_action = MeasurementAction(**msg.measurement_action)
                agent_state = SimulationAgentState.from_dict(msg.agent_state)
                measurement_req = MeasurementRequest.from_dict(measurement_action.measurement_req)
                obs = {}
                if(measurement_action.instrument_name == "Imaging SAR"):
                    obs["product_type"] = "sar"
                elif(measurement_action.instrument_name == "OLI"):
                    obs["product_type"] = "visible"
                else:
                    obs["product_type"] = "thermal"
                obs["lat"] = measurement_req.lat_lon_pos[0]
                obs["lon"] = measurement_req.lat_lon_pos[1]
                obs_str = ""
                obs_datatype = obs["product_type"]
                obs_process_time = measurement_action.t_start
                #data,raw_data_filename = self.store_raw_measurement(obs_str,obs["lat"],obs["lon"],obs_process_time)
                # if obs_datatype == "tss":
                #     processed_data = self.compute_tss_obs_value(data)
                # elif obs_datatype == "altimetry":
                #     processed_data = self.generate_altimetry()
                # elif obs_datatype == "thermal":
                #     processed_data = self.compute_thermal_obs(data)
                # else:
                #     self.log('Unsupported data type for onboard processing.')
                #     continue
                self.sd, new_data_product = self.add_data_product(self.sd,obs["lat"],obs["lon"],obs_process_time,obs_datatype,"",None)
                self.log(f'{obs_datatype} measurement data successfully saved in on-board data-base.', level=logging.INFO)
                updated_msg = "SD has been updated."
                #await self.science_reasoning_inbox.put(updated_msg)
                #await self.science_value_inbox.put(new_data_product)
                processed_item = {
                        "lat": obs["lat"],
                        "lon": obs["lon"],
                        "time": obs_process_time,
                        #"product_type": metadata["measuring_instrument"] TODO add back for ground station
                }
                self.processed_items.append(processed_item)
                await self.save_observations(obs_datatype)
        except asyncio.CancelledError:
            return

    async def teardown(self) -> None:
        # nothing to tear-down
        return
    
    # FUNCTIONS FOR ONBOARD PROCESSING

    def store_raw_measurement(self,dataprod,lat,lon,obs_process_time):
        """
        This function stores the raw data from a DataMessage prior to any preprocessing.
        It stores the raw message as a CSV identified by the lat, lon and time of the observation.
        """
        # #im = PIL.Image.open(BytesIO(base64.b64decode(dataprod))) TODO uncomment
        

        # img_np = np.array(im)
        # data = img_np[:,:,0]
        # img_np = np.delete(img_np,3,2)
        # # from https://stackoverflow.com/questions/67831382/obtaining-rgb-data-from-image-and-writing-it-to-csv-file-with-the-corresponding
        # xy_coords = np.flip(np.column_stack(np.where(np.all(img_np >= 0, axis=2))), axis=1)
        # rgb = np.reshape(img_np, (np.prod(img_np.shape[:2]), 3))

        # # Add pixel numbers in front
        # pixel_numbers = np.expand_dims(np.arange(1, xy_coords.shape[0] + 1), axis=1)
        # value = np.hstack([pixel_numbers, xy_coords, rgb])

        # Properly save as CSV
        data = np.random.rand(100,100)
        #value = np.random.rand(100,100)
        prefix = self.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
        filename = prefix+str(lat)+"_"+str(lon)+"_"+str(obs_process_time)+"_raw.csv"
        #np.savetxt(filename, value, delimiter='\t', fmt='%4d')
        return data, filename

    def compute_chlorophyll_obs_value(self,b4,b5):
        """
        Computes chlorophyll concentration using the 2BDA algorithm. TODO add reference
        """
        bda = b5 - b5/b4 + b4
        return bda

    def compute_tss_obs_value(self,b4):
        """
        Computes TSS from the paper that Molly sent me TODO add reference
        """
        tss = 195.6 * b4
        return tss

    def compute_thermal_obs(self,data):
        return data

    def generate_altimetry(self):
        """
        Generates random altimetry data until we have an altimetry data source.
        """
        return np.random.rand(100,100)

    def add_data_product(self,sd : list, lat : float, lon : float, time : float, product_type : str, filename :str, data : list):
        """
        This function adds a data product to the science database (sd) and generates a .txt header file to represent the data product.
        """
        data_product_dict = dict()
        data_product_dict["lat"] = lat
        data_product_dict["lon"] = lon
        data_product_dict["time"] = time
        data_product_dict["product_type"] = product_type
        data_product_dict["filepath"] = filename[:-8]+"_"+product_type+".csv"
        data_product_dict["checked"] = False
        if(data is not None):
            pd.DataFrame(data).to_csv(data_product_dict["filepath"],index=False,header=False)
        sd.append(data_product_dict)
        # prefix = self.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
        # filename = prefix+"dataprod"+"_"+str(lat)+"_"+str(lon)+"_"+str(time)+"_"+product_type+".txt"
        # with open(filename, mode="wt") as datafile:
        #     datafile.write(json.dumps(data_product_dict))
        return sd, data_product_dict

    async def save_observations(self,obs_type):
        """
        This function saves the lat/lon/time of all observations and all outlier observations for analysis.
        """
        hfs_coords = []
        floods_coords = []
        # lakeflood_coords = []
        # lakedrought_coords = []
        # coldlake_coords = []
        # hotlake_coords = []
        lakelevel_coords = []
        laketemp_coords = []
        bloom_coords = []
        all_coords = []
        #parent_agent = self.get_top_module()
        sat_name = self.parent_name
        for potential_outlier in self.processed_items:
            if "scenario1a" in self.scenario_dir:
                outlier, outlier_data = self.check_altimetry_outlier(potential_outlier)
            elif "scenario1b" in self.scenario_dir: 
                outlier, outlier_data = self.check_flood_outliers(potential_outlier)
                if outlier_data["event_type"] == "flood":
                    floods_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                elif outlier_data["event_type"] == "hf":
                    hfs_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            # elif "scenario2" in self.scenario_dir:
            #     all_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            #     if obs_type == "altimetry":
            #         outlier, outlier_data = self.check_lakelevel_outliers(potential_outlier)
            #         if outlier_data["event_type"] == "lake flood":
            #             lakeflood_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            #         elif outlier_data["event_type"] == "lake drought":
            #             lakedrought_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            #     if obs_type == "thermal":
            #         outlier, outlier_data = self.check_laketemp_outliers(potential_outlier)
            #         if outlier_data["event_type"] == "hot lake":
            #             hotlake_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            #         elif outlier_data["event_type"] == "cold lake":
            #             coldlake_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            #     if obs_type == "visible":
            #         bloom_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            elif "scenario2" in self.scenario_dir:
                all_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                if obs_type == "sar":
                    outlier, outlier_data = self.check_lakelevel_outliers(potential_outlier)
                    if outlier_data["event_type"] == "level":
                        lakelevel_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                elif obs_type == "thermal":
                    outlier, outlier_data = self.check_laketemp_outliers(potential_outlier)
                    if outlier_data["event_type"] == "temp":
                        laketemp_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                elif obs_type == "imagery":
                    outlier, outlier_data = self.check_bloom_outliers(potential_outlier)
                    if outlier_data["event_type"] == "bloom":
                        bloom_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                    outlier, outlier_data = self.check_laketemp_outliers(potential_outlier)
                    if outlier_data["event_type"] == "temp":
                        laketemp_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                    outlier, outlier_data = self.check_lakelevel_outliers(potential_outlier)
                    if outlier_data["event_type"] == "level":
                        lakelevel_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            
        if "scenario1b" in self.scenario_dir:
            with open(self.scenario_dir+sat_name+'_floods.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in floods_coords:
                    csv_out.writerow(row)
            with open(self.scenario_dir+sat_name+'_hfs.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in hfs_coords:
                    csv_out.writerow(row)
        #parent_agent = self.get_top_module()
        #payload = parent_agent.payload[parent_agent.name]

        instruments = []
        if "alt_sat" in self.parent_name:
            instruments.append("Imaging SAR")
        if "vnir" in self.parent_name:
            instruments.append("OLI")
        if "tir" in self.parent_name:
            instruments.append("ThermalCamera")
        if "scenario2" in self.scenario_dir:
            if "OLI" in instruments:
                with open(self.scenario_dir+sat_name+'_blooms.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in bloom_coords:
                        csv_out.writerow(row)
                with open(self.scenario_dir+sat_name+'_lakelevels.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in lakelevel_coords:
                        csv_out.writerow(row)
                with open(self.scenario_dir+sat_name+'_laketemps.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in laketemp_coords:
                        csv_out.writerow(row)
                with open(self.scenario_dir+sat_name+'_all.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in all_coords:
                        csv_out.writerow(row)
            if "Imaging SAR" in instruments:
                with open(self.scenario_dir+sat_name+'_lakelevels.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in lakelevel_coords:
                        csv_out.writerow(row)
                # with open(self.scenario_dir+sat_name+'_lakedroughts.csv','w') as out:
                #     csv_out=csv.writer(out)
                #     csv_out.writerow(['lat','lon','time'])
                #     for row in lakedrought_coords:
                #         csv_out.writerow(row)
                with open(self.scenario_dir+sat_name+'_all.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in all_coords:
                        csv_out.writerow(row)
            if "ThermalCamera" in instruments:
                with open(self.scenario_dir+sat_name+'_laketemps.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in laketemp_coords:
                        csv_out.writerow(row)
                # with open(self.scenario_dir+sat_name+'_coldlakes.csv','w') as out:
                #     csv_out=csv.writer(out)
                #     csv_out.writerow(['lat','lon','time'])
                #     for row in coldlake_coords:
                #         csv_out.writerow(row)
                with open(self.scenario_dir+sat_name+'_all.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in all_coords:
                        csv_out.writerow(row)

    # FUNCTIONS FOR SCIENCE VALUE
    
    def compute_science_value(self, lat, lon, obs):
        """
        Computes science value of a particular observation. Currently 10 for outliers, 1 for anything else.
        """
        self.log(f'Computing science value...', level=logging.DEBUG)
        outlier = False
        if "scenario1a" in self.scenario_dir:
            science_val = 1.0
            outlier, outlier_data = self.check_altimetry_outlier(obs)
            if outlier:
                science_val = 10.0
            self.log(f'Scenario 1a outlier checked!',level=logging.INFO)
        elif "scenario1b" in self.scenario_dir:
            outlier, outlier_data = self.parent_module.check_flood_outliers(obs)
            science_val = outlier_data["severity"]
            self.log(f'Scenario 1b outlier checked!',level=logging.INFO)
        elif "scenario2" in self.scenario_dir:
            if obs["product_type"] == "sar":
                outlier, outlier_data = self.check_lakelevel_outliers(obs)
                science_val = outlier_data["severity"]
                self.log(f'Scenario 2 lake level outlier checked!',level=logging.DEBUG)
            elif obs["product_type"] == "thermal":
                outlier, outlier_data = self.check_laketemp_outliers(obs)
                science_val = outlier_data["severity"]
                self.log(f'Scenario 2 lake temp outlier checked!',level=logging.DEBUG)
            elif obs["product_type"] == "visible":
                outlier, outlier_data = self.check_bloom_outliers(obs)
                science_val = outlier_data["severity"]
                self.log(f'Scenario 2 bloom outlier checked!',level=logging.DEBUG)
            else:
                science_val = 0.0
        else:
            science_val = 0.0
        if outlier:
            self.log(f'Computed bonus science value: {science_val}', level=logging.INFO)
            outlier = True
        else:
            self.log(f'Computed normal science value: {science_val}', level=logging.INFO)
        resulting_value = science_val*self.meas_perf()
        return resulting_value, outlier_data

    def get_pop(self, lat, lon, points):
        """
        Gets population from CSV data (originally from hydroATLAS)
        """
        pop = 0.0
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                pop = points[i,4]
                break
        return pop

    def get_data_product(self, lat, lon, product_type):
        """
        Gets data product from science database based on latitude, longitude and product type. TODO add time as a parameter.
        """
        exists = False
        for item in self.sd:
            if item["lat"] == lat and item["lon"] == lon and item["product_type"]==product_type:
                if(item["filepath"].lower().endswith('.csv')):
                    self.log("Found data product!",level=logging.DEBUG)
                    exists = True
                else:
                    self.log("Found data product but file type not supported")
            else:
                self.log("Could not find data product")
        return exists
    

    def get_flood_chance(self, lat, lon, points):
        """
        Gets flood chance from CSV data.
        """
        flood_chance = None
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                flood_chance = points[i, 3] # change this back to 5 for chlorophyll_baseline.csv
                lat = points[i, 0]
                lon = points[i, 1]
                break
        return flood_chance, lat, 


    def check_tss_outlier(self,item):
        """
        Checks TSS data for outliers. Currently hardcoded. TODO use real data source.
        """
        outlier = False
        mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], self.parent_module.points)
        if mean > 30000: # TODO remove this hardcode
            self.log(f'TSS outlier measured at {lat}, {lon}!',level=logging.INFO)
            outlier = True
        else:
            self.log(f'No TSS outlier measured at {lat}, {lon}',level=logging.INFO)
        item["checked"] = True
        return outlier

    def get_mean_sd(self, lat, lon, points):
        """
        Computes mean and standard deviation from CSV data.
        """
        mean = None
        sd = None
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                mean = points[i, 2]
                sd = points[i, 3]
                lat = points[i, 0]
                lon = points[i, 1]
                break
        return mean, sd, lat, lon
    
    def check_altimetry_outlier(self,item):
        """
        Checks altimetry data for outliers. Currently hardcoded. TODO use real data source.
        """
        outlier = False
        outlier_data = None
        if(item["checked"] is False):
            flood_chance, lat, lon = self.get_flood_chance(item["lat"], item["lon"], self.points)
            if flood_chance > 0.50: # TODO remove this hardcode
                item["severity"] = flood_chance
                outlier = True
                outlier_data = item
                self.log(f'Flood detected at {lat}, {lon}!',level=logging.INFO)
            else:
                self.log(f'No flood detected at {lat}, {lon}',level=logging.INFO)
            item["checked"] = True
        return outlier, outlier_data
    
    def check_bloom_outliers(self,item):
        """
        Checks G-REALM data for outliers. To be used for Scenario 2.
        """
        outlier = False
        outlier_data = None
        severity = 0.0
        event_type = ""
        lake_obs = []
        for i in range(len(self.points[:, 0])):
            if (abs(float(item["lat"])-self.points[i, 0]) < 0.001) and (abs(float(item["lon"]) - self.points[i, 1]) < 0.001):
                if self.points[i,5] == 0:
                    lake_obs.append(self.points[i,:])
        if len(lake_obs) == 0:
            item["severity"] = 0.0
            item["event_type"] = ""
            return outlier, item
        latest_obs = None
        for obs in lake_obs:
            obs_start = obs[2]
            obs_duration = obs[3]
            if(self.get_current_time() > obs_start) and (self.get_current_time() < (obs_start+obs_duration)):
                latest_obs = obs
        if latest_obs is None:
            return False, None
        
        # if latest_obs[5] > (latest_obs[2]+latest_obs[3]):
        #     if latest_obs[3] == 0.0:
        #         item["severity"] = np.abs(latest_obs[5]/latest_obs[3])
        #     else:
        item["severity"] = latest_obs[4]
        outlier = True
        outlier_data = item
        outlier_data["event_type"] = "bloom"
        self.log(f'Algal bloom detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        # else:
        #     outlier_data = item
        #     outlier_data["severity"] = 0.0
        #     outlier_data["event_type"] = ""
        #     self.log(f'No algal bloom detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        return outlier, outlier_data

    def check_lakelevel_outliers(self,item):
        """
        Checks G-REALM data for outliers. To be used for Scenario 2.
        """
        outlier = False
        outlier_data = None
        severity = 0.0
        event_type = ""
        lake_obs = []
        for i in range(len(self.points[:, 0])):
            if (abs(float(item["lat"])-self.points[i, 0]) < 0.01) and (abs(float(item["lon"]) - self.points[i, 1]) < 0.01):
                if self.points[i,5] == 2:
                    lake_obs.append(self.points[i,:])
        if len(lake_obs) == 0:
            item["severity"] = 0.0
            item["event_type"] = ""
            return outlier, item
        if len(lake_obs) == 0:
            item["severity"] = 0.0
            item["event_type"] = ""
            return outlier, item
        latest_obs = None
        for obs in lake_obs:
            obs_start = obs[2]
            obs_duration = obs[3]
            if(self.get_current_time() > obs_start) and (self.get_current_time() < (obs_start+obs_duration)):
                latest_obs = obs
        if latest_obs is None:
            return False, None
        
        item["severity"] = latest_obs[4]
        outlier = True
        outlier_data = item
        outlier_data["event_type"] = "level"
        self.log(f'Lake flood detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        # elif latest_obs[5] < (latest_obs[2]-latest_obs[3]):
        #     if latest_obs[3] == 0.0:
        #         item["severity"] = np.abs(latest_obs[5]/latest_obs[3])
        #     else:
        #         item["severity"] = latest_obs[5]
        #     outlier = True
        #     outlier_data = item
        #     outlier_data["event_type"] = "lake drought"
        #     self.log(f'Lake drought detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        # else:
        #     outlier_data = item
        #     outlier_data["severity"] = 0.0
        #     outlier_data["event_type"] = ""
        #     self.log(f'No lake height outlier detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        return outlier, outlier_data

    def check_laketemp_outliers(self,item):
        """
        Checks G-REALM data for outliers. To be used for Scenario 2.
        """
        outlier = False
        outlier_data = None
        severity = 0.0
        event_type = ""
        lake_obs = []
        for i in range(len(self.points[:, 0])):
            if (abs(float(item["lat"])-self.points[i, 0]) < 0.01) and (abs(float(item["lon"]) - self.points[i, 1]) < 0.01):
                if self.points[i,5] == 1:
                    lake_obs.append(self.points[i,:])
        if len(lake_obs) == 0:
            item["severity"] = 0.0
            item["event_type"] = ""
            return outlier, item
        latest_obs = None
        for obs in lake_obs:
            obs_start = obs[2]
            obs_duration = obs[3]
            if(self.get_current_time() > obs_start) and (self.get_current_time() < (obs_start+obs_duration)):
                latest_obs = obs
        if latest_obs is None:
            return False, None
        
        item["severity"] = latest_obs[4]
        outlier = True
        outlier_data = item
        outlier_data["event_type"] = "temp"
        self.log(f'Lake temperature event detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        # elif latest_obs[5] < (latest_obs[2]-latest_obs[3]):
        #     if latest_obs[3] == 0.0:
        #         item["severity"] = np.abs(latest_obs[5]/latest_obs[3])
        #     else:
        #         item["severity"] = latest_obs[5]
        #     outlier = True
        #     outlier_data = item
        #     outlier_data["event_type"] = "cold lake"
        #     self.log(f'Cold lake detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        # else:
        #     outlier_data = item
        #     outlier_data["severity"] = 0.0
        #     outlier_data["event_type"] = ""
        #     self.log(f'No lake temperature outlier detected at {latest_obs[0]}, {latest_obs[1]}',level=logging.DEBUG)
        return outlier, outlier_data

    def meas_perf(self):
        """
        Evaluates the measurement performance based on the parameters of the satellite and payload.
        """
        # Coefficients taken from Molly Stroud's work
        a = 8.94e-5
        b = 1.45e-3
        c = 0.164
        d = 1.03
        a1 = 1.97e-6
        b1 = -0.007
        a2 = -1.42e-6
        b2 = 3.08e-4
        c1 = 13.14
        c2 = -2.81e-2
        d2 = 1.03
        snr = 10
        spatial_res = 10
        spectral_res = 10
        x = snr
        y = spatial_res
        z = spectral_res
        meas = a*x-b*y-c*np.log10(z)+d
        spatial = a1*pow(np.e,(b1*y+c1))
        perf = 0.75*meas+0.25*spatial # modify to include temporal res at some point
        self.log(f'Measurement performance: {perf}',level=logging.DEBUG)
        return perf