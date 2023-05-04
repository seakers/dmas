import csv
import math
import numpy as np
import pandas as pd
from messages import *
from states import SimulationAgentState
from tasks import *
from zmq import asyncio as azmq
from dmas.agents import AgentAction
from dmas.modules import *

class ScienceModuleTypes(Enum):
    SCENARIO1 = 'SCENARIO1' 
    SCENARIO2 = 'SCENARIO2'

class ScienceModule(InternalModule):
    def __init__(self, 
                results_path : str, 
                manager_port : int,
                agent_id : int,
                parent_network_config: NetworkConfig, 
                science_module_type : ScienceModuleTypes,
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        module_network_config =  NetworkConfig(f'AGENT_{agent_id}',
                                                manager_address_map = {
                                                zmq.REQ: [],
                                                zmq.PUB: [f'tcp://*:{manager_port+6 + 4*agent_id + 3}'],
                                                zmq.SUB: [f'tcp://localhost:{manager_port+6 + 4*agent_id + 2}'],
                                                zmq.PUSH: [f'tcp://localhost:{manager_port+3}']})
                
        super().__init__(f'SCIENCE_MODULE_{agent_id}', 
                        module_network_config, 
                        parent_network_config, 
                        level, 
                        logger)
        
        if science_module_type not in ScienceModuleTypes:
            raise NotImplementedError(f'planner of type {science_module_type} not yet supported.')
        self.science_module_type = science_module_type
        self.results_path = results_path
        self.parent_id = agent_id

    async def sim_wait(self, delay: float) -> None:
        return

    async def empty_manager_inbox(self) -> list:
        msgs = []
        while True:
            # wait for manager messages
            self.log('waiting for parent agent message...')
            _, _, content = await self.manager_inbox.get()
            msgs.append(content)

            # wait for any current transmissions to finish being received
            self.log('waiting for any possible transmissions to finish...')
            await asyncio.sleep(0.01)

            if self.manager_inbox.empty():
                self.log('manager queue empty.')
                break
            self.log('manager queue still contains elements.')
        
        return msgs

class Scenario1ScienceModule(ScienceModule):
    def __init__(self, 
                results_path : str, 
                manager_port: int, 
                agent_id: int, 
                parent_network_config: NetworkConfig, 
                level: int = logging.INFO, 
                logger: logging.Logger = None
                ) -> None:
        super().__init__(results_path,
                         manager_port, 
                         agent_id, 
                         parent_network_config, 
                         ScienceModuleTypes.SCENARIO1, 
                         level, 
                         logger)
        
    async def setup(self) -> None:
        
        # setup internal inboxes
        self.science_value_inbox = asyncio.Queue()
        self.science_reasoning_inbox = asyncio.Queue()
        self.onboard_processing_inbox = asyncio.Queue()
        self.processed_items = []
        self.sd = []
        self.points = np.zeros(shape=(1000, 4))
        with open('/home/ben/repos/dmaspy/scenarios/scenario1_agile/resources/riverATLAS.csv') as csvfile:
            reader = csv.reader(csvfile)
            count = 0
            for row in reader:
                if count == 0:
                    count = 1
                    continue
                self.points[count-1,:] = [row[0], row[1], row[2], row[3]]
                count = count + 1
        self.log('done w/ setup',level=logging.WARNING)
        
    async def live(self) -> None:
        """
        Performs concurrent tasks:
        - Listener: receives messages from the parent agent and checks results
        - Science valuer: determines value of a given measurement
        - Science reasoning: checks data for outliers
        - Onboard processing: converts data of one type into data of another type (e.g. level 0 to level 1)
        """
        self.log('starting tasks',level=logging.WARNING)
        listener_task = asyncio.create_task(self.listener(), name='listener()')
        science_value_task = asyncio.create_task(self.science_value(), name='science_value()')
        #science_reasoning_task = asyncio.create_task(self.science_reasoning(), name='science_reasoning()')
        #onboard_processing_task = asyncio.create_task(self.onboard_processing(), name='onboard_processing()')
        
        # , science_value_task, science_reasoning_task, onboard_processing_task
        tasks = [listener_task,science_value_task]
        
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task : asyncio.Task
            task.cancel()
            print("cancelling tasks")
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
                sockets = dict(await poller.poll())

                if manager_socket in sockets:
                    self.log('listening to manager broadcast!')
                    _, _, content = await self.listen_manager_broadcast()

                    # if sim-end message, end agent `live()`
                    if content['msg_type'] == ManagerMessageTypes.SIM_END.value:
                        self.log(f"received manager broadcast or type {content['msg_type']}! terminating `live()`...")
                        return

                    elif content['msg_type'] == SimulationMessageTypes.AGENT_STATE.value:
                        # unpack message 
                        msg : AgentStateMessage = AgentStateMessage(**content)
                        
                        # send to bundle builder 
                        print('Received agent state in science module!')
                        await self.science_value_inbox.put(msg)

                    elif content['msg_type'] == SimulationMessageTypes.TASK_REQ.value:
                        # unpack message
                        task_req = TaskRequest(**content)

                        # create task bid from task request and add to results
                        task_dict : dict = task_req.task
                        task = MeasurementTask(**task_dict)
                        print("received task request in science module")

                    # else, let agent handle it
                    else:
                        self.log(f"received manager broadcast or type {content['msg_type']}! ignoring...")
        
        except asyncio.CancelledError:
            print("Asyncio cancelled error in science module listener")
            return
        
    async def science_value(self):
        try:
            while True:
                msg = await self.science_value_inbox.get()
                print("got msg!")
                print(msg)
                lat = msg.content["lat"]
                lon = msg.content["lon"]
                obs = msg.content
                print(obs)
                science_value, outlier = self.compute_science_value(lat, lon, obs)
                print(science_value)
                self.log('Computed the science value!')
                metadata = {
                    "observation" : obs
                }
                desired_variables = []
                # if "scenario1a" in self.parent_module.scenario_dir:
                #     desired_variables = ["visible"]
                # elif "scenario1b" in self.parent_module.scenario_dir:
                #     desired_variables = ["visible","altimetry"]
                # elif "scenario2" in self.parent_module.scenario_dir:
                #     desired_variables = ["visible"]
                # else:
                #     self.log(f'Scenario not supported by request_handler',level=logging.INFO)
                # measurement_request = MeasurementRequest(desired_variables, lat, lon, science_value, metadata)

                # req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
                # ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, measurement_request)
                # if self.parent_module.notifier == "True":
                #     await self.send_internal_message(req_msg)
                #     await self.send_internal_message(ext_msg)
                #     self.log(f'Sent message to transmitter!',level=logging.DEBUG)
        except Exception as e:
            print(e)
            e.printStackTrace()
        except asyncio.CancelledError:
            return
        
    async def science_reasoning(self):
        try:
            while True:
                print("in science reasoning")
                msg = await self.science_reasoning_inbox.get()
                outliers = []
                for item in self.sd:
                    if(item["product_type"] == "visible"):
                        self.log(f'TSS data not checked for outliers.',level=logging.DEBUG)
                        #outlier, outlier_data = self.check_tss_outliers(item)
                        #if outlier is True:
                        #    outliers.append(outlier_data)
                    elif(item["product_type"] == "altimetry"):
                        if item["checked"] is False:
                            if "scenario1a" in self.parent_module.scenario_dir:
                                outlier, outlier_data = self.parent_module.check_altimetry_outlier(item)
                            if "scenario1b" in self.parent_module.scenario_dir:
                                outlier, outlier_data = self.parent_module.check_flood_outliers(item)
                            if "scenario2" in self.parent_module.scenario_dir:
                                outlier, outlier_data = self.parent_module.check_lakelevel_outliers(item)
                            if outlier is True:
                                self.log(f'Altimetry outlier in check_sd',level=logging.DEBUG)
                                outliers.append(outlier_data)
                            item["checked"] = True
                    elif(item["product_type"] == "thermal"):
                        if item["checked"] is False:
                            if "scenario2" in self.parent_module.scenario_dir:
                                outlier, outlier_data = self.parent_module.check_laketemp_outliers(item)
                            if outlier is True:
                                self.log(f'Thermal outlier in check_sd',level=logging.INFO)
                                outliers.append(outlier_data)
                            item["checked"] = True 
                    else:
                        self.log(f'Item in science database unsupported by science processing module.',level=logging.DEBUG)
                for outlier in outliers:
                    self.log(f'Outliers: {outlier}',level=logging.INFO)
                    msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, outlier)
                    await self.send_internal_message(msg)
        except asyncio.CancelledError:
            return
        
    async def onboard_processing(self):
        try:
            while True:
                print("in onboard processing")
                raw_data = await self.onboard_processing_inbox.get()
                obs_str = raw_data.get_data()
                lat, lon = raw_data.get_target()
                obs_datatype = raw_data.get_datatype()
                obs_process_time = self.get_current_time()
                data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time)
                if obs_datatype == "tss":
                    processed_data = self.compute_tss_obs_value(data)
                elif obs_datatype == "altimetry":
                    processed_data = self.generate_altimetry()
                elif obs_datatype == "thermal":
                    processed_data = self.compute_thermal_obs(data)
                else:
                    self.log('Unsupported data type for onboard processing.')
                    continue
                self.sd, new_data_product = self.add_data_product(self.sd,lat,lon,obs_process_time,obs_datatype,raw_data_filename,processed_data)
                self.log(f'{obs_datatype} measurement data successfully saved in on-board data-base.', level=logging.DEBUG)
                updated_msg = "SD has been updated."
                print(updated_msg)
                await self.science_reasoning_inbox.put(updated_msg)
                await self.science_value_inbox.put(new_data_product)
                processed_item = {
                        "lat": lat,
                        "lon": lon,
                        "time": raw_data.get_metadata()["time"],
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
        value = np.random.rand(100,100)
        prefix = self.parent_module.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
        filename = prefix+str(lat)+"_"+str(lon)+"_"+str(obs_process_time)+"_raw.csv"
        np.savetxt(filename, value, delimiter='\t', fmt='%4d')
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

    def add_data_product(self,sd,lat,lon,time,product_type,filename,data):
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
        prefix = self.parent_module.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
        filename = prefix+"dataprod"+"_"+str(lat)+"_"+str(lon)+"_"+str(time)+"_"+product_type+".txt"
        with open(filename, mode="wt") as datafile:
            datafile.write(json.dumps(data_product_dict))
        return sd, data_product_dict

    async def save_observations(self,obs_type):
        """
        This function saves the lat/lon/time of all observations and all outlier observations for analysis.
        """
        hfs_coords = []
        floods_coords = []
        lakeflood_coords = []
        lakedrought_coords = []
        coldlake_coords = []
        hotlake_coords = []
        bloom_coords = []
        all_coords = []
        parent_agent = self.get_top_module()
        sat_name = parent_agent.name
        for potential_outlier in self.processed_items:
            if "scenario1a" in self.parent_module.scenario_dir:
                outlier, outlier_data = self.parent_module.check_altimetry_outlier(potential_outlier)
            elif "scenario1b" in self.parent_module.scenario_dir: 
                outlier, outlier_data = self.parent_module.check_flood_outliers(potential_outlier)
                if outlier_data["event_type"] == "flood":
                    floods_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                elif outlier_data["event_type"] == "hf":
                    hfs_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            elif "scenario2" in self.parent_module.scenario_dir:
                all_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                if obs_type == "altimetry":
                    outlier, outlier_data = self.parent_module.check_lakelevel_outliers(potential_outlier)
                    if outlier_data["event_type"] == "lake flood":
                        lakeflood_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                    elif outlier_data["event_type"] == "lake drought":
                        lakedrought_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                if obs_type == "thermal":
                    outlier, outlier_data = self.parent_module.check_laketemp_outliers(potential_outlier)
                    if outlier_data["event_type"] == "hot lake":
                        hotlake_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                    elif outlier_data["event_type"] == "cold lake":
                        coldlake_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
                if obs_type == "visible":
                    bloom_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
            
        if "scenario1b" in self.parent_module.scenario_dir:
            with open(self.parent_module.scenario_dir+sat_name+'_floods.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in floods_coords:
                    csv_out.writerow(row)
            with open(self.parent_module.scenario_dir+sat_name+'_hfs.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in hfs_coords:
                    csv_out.writerow(row)
        parent_agent = self.get_top_module()
        payload = parent_agent.payload[parent_agent.name]
        instruments = []
        if isinstance(payload, list):
            for i in range(len(payload)):
                instruments.append(payload[i]["name"])
        else:
            instruments.append(payload["name"])
        if "scenario2" in self.parent_module.scenario_dir:
            if "OLI" in instruments:
                with open(self.parent_module.scenario_dir+sat_name+'_blooms.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in lakeflood_coords:
                        csv_out.writerow(row)
                with open(self.parent_module.scenario_dir+sat_name+'_all.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in all_coords:
                        csv_out.writerow(row)
            if "POSEIDON-3B Altimeter" in instruments:
                with open(self.parent_module.scenario_dir+sat_name+'_lakefloods.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in lakeflood_coords:
                        csv_out.writerow(row)
                with open(self.parent_module.scenario_dir+sat_name+'_lakedroughts.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in lakedrought_coords:
                        csv_out.writerow(row)
                with open(self.parent_module.scenario_dir+sat_name+'_all.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in all_coords:
                        csv_out.writerow(row)
            if "ThermalCamera" in instruments:
                with open(self.parent_module.scenario_dir+sat_name+'_hotlakes.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in hotlake_coords:
                        csv_out.writerow(row)
                with open(self.parent_module.scenario_dir+sat_name+'_coldlakes.csv','w') as out:
                    csv_out=csv.writer(out)
                    csv_out.writerow(['lat','lon','time'])
                    for row in coldlake_coords:
                        csv_out.writerow(row)
                with open(self.parent_module.scenario_dir+sat_name+'_all.csv','w') as out:
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
        science_val = 1.0
        outlier, outlier_data = self.check_altimetry_outlier(obs)
        if outlier:
            science_val = 10.0
        self.log(f'Scenario 1a outlier checked!',level=logging.INFO)
        # if "scenario1a" in self.parent_module.scenario_dir:
        #     science_val = 1.0
        #     outlier, outlier_data = self.check_altimetry_outlier(obs)
        #     if outlier:
        #         science_val = 10.0
        #     self.log(f'Scenario 1a outlier checked!',level=logging.INFO)
        # elif "scenario1b" in self.parent_module.scenario_dir:
        #     outlier, outlier_data = self.parent_module.check_flood_outliers(obs)
        #     science_val = outlier_data["severity"]
        #     self.log(f'Scenario 1b outlier checked!',level=logging.INFO)
        # elif "scenario2" in self.parent_module.scenario_dir:
        #     if obs["product_type"] == "altimetry":
        #         outlier, outlier_data = self.parent_module.check_lakelevel_outliers(obs)
        #         science_val = outlier_data["severity"]
        #         self.log(f'Scenario 2 lake level outlier checked!',level=logging.INFO)
        #     elif obs["product_type"] == "thermal":
        #         outlier, outlier_data = self.parent_module.check_laketemp_outliers(obs)
        #         science_val = outlier_data["severity"]
        #         self.log(f'Scenario 2 lake temp outlier checked!',level=logging.INFO)
        #     else:
        #         science_val = 1.0
        if outlier:
            self.log(f'Computed bonus science value: {science_val}', level=logging.DEBUG)
            outlier = True
        else:
            self.log(f'Computed normal science value: {science_val}', level=logging.DEBUG)
        resulting_value = science_val*self.meas_perf()
        return resulting_value, outlier

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