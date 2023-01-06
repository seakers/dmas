import asyncio
import json
import logging
import os
import pandas as pd
import numpy as np
import csv
import base64
import random
import PIL.Image
from io import BytesIO
from modules import Module
from messages import *
from utils import ScienceSubmoduleTypes
from tasks import InformationRequest, DataProcessingRequest, MeasurementRequest

class ScienceModule(Module):
    def __init__(self, parent_agent : Module, scenario_dir : str, predictive_model : bool) -> None:
        super().__init__(AgentModuleTypes.SCIENCE_MODULE.value, parent_agent, [], 0)

        self.scenario_dir = scenario_dir

        parent_agent = self.get_top_module()
        data = dict()
        spacecraft_list = parent_agent.mission_dict.get('spacecraft')
        for spacecraft in spacecraft_list:
            name = spacecraft.get('name')
            # land coverage data metrics data
            mission_profile = spacecraft.get('missionProfile')
            data[name] = mission_profile
        if parent_agent.name == "Central Node":
            self.mission_profile = None
        else:
            self.mission_profile = data[parent_agent.name]
        self.chl_points = np.zeros(shape=(2000, 6))
        with open(self.scenario_dir+'chlorophyll_baseline.csv') as csvfile:
            reader = csv.reader(csvfile)
            count = 0
            for row in reader:
                if count == 0:
                    count = 1
                    continue
                self.chl_points[count-1,:] = [row[0], row[1], row[2], row[3], row[4], row[5]]
                count = count + 1

        data_products = self.load_data_products()        

        self.submodules = [
            OnboardProcessingModule(self, data_products),            
            ScienceReasoningModule(self, data_products),
            ScienceValueModule(self, data_products)
        ]
        if predictive_model:
            self.submodules.append(SciencePredictiveModelModule(self,data_products))

    def load_data_products(self) -> list:
        data_products = []

        for file in os.listdir(self.scenario_dir):
            if(file.lower().endswith('.txt')):
                with open(file) as headerfile:
                    data_product_dict = json.load(headerfile)
                    data_products.append(data_product_dict)

        return data_products

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg.dst_module
            if dst_name != self.name:
                # This module is NOT the intended receiver for this message. Forwarding to rightful destination
                await self.send_internal_message(msg)
            else:
                # This module is the intended receiver for this message. Handling message

                if isinstance(msg, DataMessage):
                    # if a data message is received, forward to on-board processing submodule
                    self.log(f'Received Data message from \'{msg.src_module}\'!')
                    msg.dst_module = ScienceSubmoduleTypes.ONBOARD_PROCESSING.value

                    await self.send_internal_message(msg)

                elif isinstance(msg, MeasurementRequestMessage) and isinstance(msg.get_request(), InformationRequest):
                    # if a request message is received, forward to on-board processing submodule
                    self.log(f'Received Information Request message from \'{msg.src_module}\'!')
                    msg.dst_module = ScienceSubmoduleTypes.ONBOARD_PROCESSING.value

                    await self.send_internal_message(msg)

                elif isinstance(msg, MeasurementRequestMessage) and isinstance(msg.get_request(), DataProcessingRequest):
                    # if a request message is received, forward to on-board processing submodule
                    self.log(f'Received Data Processing Request message from \'{msg.src_module}\'!')
                    msg.dst_module = ScienceSubmoduleTypes.ONBOARD_PROCESSING.value

                    await self.send_internal_message(msg)

                elif isinstance(msg.content, InterNodeDownlinkMessage):
                    downlink_msg = msg.content
                    obs = DataMessage.from_dict(json.loads(downlink_msg.content))
                    obs.dst_module = ScienceSubmoduleTypes.ONBOARD_PROCESSING.value
                    await self.send_internal_message(obs)

                else:
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.',level=logging.INFO)

        except asyncio.CancelledError:
            return


class ScienceValueModule(Module):
    def __init__(self, parent_module : Module, sd) -> None:
        super().__init__(ScienceSubmoduleTypes.SCIENCE_VALUE.value, 
                         parent_module, 
                         submodules=[],
                         n_timed_coroutines=0)
        self.sd = sd
        self.unvalued_queue = []
        self.valued_queue = []
        self.model_requests_queue = []
        self.model_results_queue = []
        self.prop_meas_obs_metrics = []
        self.science_value_sum = 0

    async def activate(self):
        await super().activate()

        self.request_msg_queue = asyncio.Queue()
        self.meas_msg_queue = asyncio.Queue()

    async def internal_message_handler(self, msg: InternalMessage):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module == ScienceSubmoduleTypes.SCIENCE_REASONING.value):
                # Event of interest sent from the science reasoning module
                await self.request_msg_queue.put(msg)
            elif(msg.src_module == ScienceSubmoduleTypes.SCIENCE_PREDICTIVE_MODEL.value):
                # receiving result from science predictive models module
                self.model_results_queue.append(msg)
            elif(msg.src_module == ScienceSubmoduleTypes.ONBOARD_PROCESSING.value):
                await self.meas_msg_queue.put(msg)
            else:
                self.log(f'Unsupported message type for this module.')

            # event-driven
            
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        """
        Executes list of coroutine tasks to be executed by the science value module. These coroutine task incluide:
        """
        try:
            # compute_science_value = asyncio.create_task(self.compute_science_value())
            # compute_science_value.set_name('compute_science_value')
            # broadcast_meas_req = asyncio.create_task(self.broadcast_meas_req())
            # broadcast_meas_req.set_name('broadcast_meas_req')
            request_handler = asyncio.create_task(self.request_handler())
            request_handler.set_name('request_handler')

            meas_handler = asyncio.create_task(self.meas_handler())
            meas_handler.set_name('meas_handler')

            coroutines = [request_handler,meas_handler]

            done, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)

            done_name = None
            for coroutine in done:
                coroutine : asyncio.Task
                done_name = coroutine.get_name()
                self.log(f"{done_name} completed!")

            for p in pending:
                p : asyncio.Task
                self.log(f"Terminating {p.get_name()}...")
                p.cancel()
                await p
        
        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    async def request_handler(self):
        try:
            while True:
                msg : DataMessage = await self.request_msg_queue.get()
                lat = msg.content["lat"]
                lon = msg.content["lon"]
                obs = msg.content

                science_value, outlier = self.compute_science_value(lat, lon, obs)                
                metadata = {
                    "altimetry" : obs
                }
                measurement_request = MeasurementRequest("tss", lat, lon, science_value, metadata)

                req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
                ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, measurement_request)
                await self.send_internal_message(req_msg)
                await self.send_internal_message(ext_msg)
                self.log(f'Sent message to transmitter!',level=logging.DEBUG)

        except asyncio.CancelledError:
            return

    async def meas_handler(self):
        try:
            oli_outlier_count = 0
            jason_outlier_count = 0
            coobs_outlier_count = 0
            while True:
                msg : DataMessage = await self.meas_msg_queue.get()
                lat = msg.content["lat"]
                lon = msg.content["lon"]
                obs = msg.content
                metadata = msg.content["metadata"]

                science_value, outlier = self.compute_science_value(lat, lon, obs)
                parent_agent = self.get_top_module()
                instrument = parent_agent.payload[parent_agent.name]["name"]                
                if outlier is True and instrument == "OLI": # TODO fix this hardcode
                    oli_outlier_count+=1
                    self.log(f'Landsat outlier count: {oli_outlier_count}',level=logging.DEBUG)
                if outlier is True and instrument == "POSEIDON-3B Altimeter": # TODO fix this hardcode
                    jason_outlier_count+=1
                    self.log(f'Jason outlier count: {jason_outlier_count}',level=logging.DEBUG)
                if outlier is True and instrument == "OLI" and metadata:
                    coobs_outlier_count+=1
                    self.log(f'Co-obs outlier count: {coobs_outlier_count}',level=logging.DEBUG)
                
                self.log(f'Received measurement with value {science_value}!',level=logging.DEBUG)
                self.science_value_sum = self.science_value_sum + science_value
                self.log(f'Sum of science values: {self.science_value_sum}',level=logging.DEBUG)
                self.log(f'Sum of science values: {self.science_value_sum}', logger_type=LoggerTypes.RESULTS, level=logging.DEBUG)

        except asyncio.CancelledError:
            return

    def compute_science_value(self, lat, lon, obs):
        self.log(f'Computing science value...', level=logging.DEBUG)
        outlier = False

        science_val = 1.0 #self.get_pop(lat, lon, points) TODO replace this?
        flood, flood_data = self.check_altimetry_outlier(obs)
        if(flood):
            science_val = science_val * 10
            self.log(f'Computed bonus science value: {science_val}', level=logging.DEBUG)
            outlier = True
        else:
            self.log(f'Computed normal science value: {science_val}', level=logging.DEBUG)
        return science_val*self.meas_perf(), outlier

    def get_pop(self, lat, lon, points):
        pop = 0.0
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                pop = points[i,4]
                break
        return pop

    def get_flood_chance(self, lat, lon, points):
        flood_chance = None
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                flood_chance = points[i, 5]
                lat = points[i, 0]
                lon = points[i, 1]
                break
        return flood_chance, lat, lon

    def get_data_product(self, lat, lon, product_type):
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


    def check_tss_outlier(self,item):
        outlier = False
        mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], self.parent_module.chl_points)
        if mean > 30000: # TODO remove this hardcode
            self.log(f'TSS outlier measured at {lat}, {lon}!',level=logging.INFO)
            outlier = True
        else:
            self.log(f'No TSS outlier measured at {lat}, {lon}',level=logging.INFO)
        item["checked"] = True
        return outlier

    def check_altimetry_outlier(self,item):
        outlier = False
        outlier_data = None
        if(item["checked"] is False):
            flood_chance, lat, lon = self.get_flood_chance(item["lat"], item["lon"], self.parent_module.chl_points)
            if flood_chance > 0.95: # TODO remove this hardcode
                item["severity"] = flood_chance
                outlier = True
                outlier_data = item
                self.log(f'Flood detected at {lat}, {lon}!',level=logging.INFO)
            else:
                self.log(f'No flood detected at {lat}, {lon}',level=logging.INFO)
            item["checked"] = True
        return outlier, outlier_data

    def get_mean_sd(self, lat, lon, points):
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

    def meas_perf(self):
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
        parent_agent = self.get_top_module()
        instrument = parent_agent.payload[parent_agent.name]["name"]
        if(instrument=="VIIRS" or instrument=="OLI"):
            x = parent_agent.payload[parent_agent.name]["snr"]
            y = parent_agent.payload[parent_agent.name]["spatial_res"]
            z = parent_agent.payload[parent_agent.name]["spectral_res"]
            meas = a*x-b*y-c*np.log10(z)+d
            spatial = a1*pow(np.e,(b1*y+c1))
            perf = 0.75*meas+0.25*spatial # modify to include temporal res at some point
        else:
            perf = 1
        self.log(f'Measurement performance: {perf}',level=logging.DEBUG)
        return perf


class OnboardProcessingModule(Module):
    def __init__(self, parent_module : Module, sd : list) -> None:
        self.sd : list = sd
        super().__init__(ScienceSubmoduleTypes.ONBOARD_PROCESSING.value, parent_module, submodules=[],
                         n_timed_coroutines=0)

        self.meas_results = []
        self.data_processing_requests = []
        self.downlink_items = []
        self.tss_count = 0 # TODO remove

    async def activate(self):
        await super().activate()

        # incoming message queues
        self.incoming_results = asyncio.Queue()

        # events
        self.updated = asyncio.Event()
        self.database_lock = asyncio.Lock()


    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if isinstance(msg, DataMessage):
                # event-driven
                self.log(f'Received new observation data! Processing...', level=logging.DEBUG)            
                await self.incoming_results.put(msg)
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
            ## Internal coroutines
            process_meas_results = asyncio.create_task(self.process_meas_results())
            process_meas_results.set_name (f'{self.name}_process_meas_results')
            coroutines.append(process_meas_results)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    done_name = coroutine.get_name()

            # cancel all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine : asyncio.Task
                subroutine.cancel()
                await subroutine
            
        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    async def process_meas_results(self):
        try:
            while True:
                # for i in range(len(self.meas_results)):
                #     meas_result = self.meas_results[i].content
                #     lat = meas_result.lat
                #     lon = meas_result.lon
                #     self.log(f'Received measurement result from ({lat}°, {lon}°)!')
                #     b4,b5,prefix,stored_data_filepath = self.store_measurement(meas_result.obs)
                #     processed_data = self.compute_chlorophyll_obs_value(b4,b5)
                #     self.sd = self.add_data_product(self.sd,lat,lon,0.01,"chlorophyll-a",prefix+"chla_"+stored_data_filepath,processed_data)
                #     self.meas_results.pop(i)
                # await self.sim_wait(1.0)
                if self.updated.is_set():
                   self.updated.clear() 

                # wait for next measurement result to come in
                msg : DataMessage = await self.incoming_results.get()
                acquired = await self.database_lock.acquire()

                # unpackage result
                obs_str = msg.get_data()
                lat, lon = msg.get_target()
                metadata = msg.get_metadata()
                self.log(f'Received measurement result from ({lat}°, {lon}°) taken at time {metadata["time"]}!', level=logging.INFO)



                # process result
                obs_process_time = self.get_current_time()

                parent_agent = self.get_top_module()
                instrument = parent_agent.payload[parent_agent.name]["name"]
                
                # if(instrument != "Ground Sensor"):
                #     metadata["measuring_instrument"] = instrument
                #     msg.metadata = metadata
                #     self.log(f'Message to be downlinked: {msg}',level=logging.DEBUG)
                #     downlink_message = InterNodeDownlinkMessage(self,"Central Node",msg)
                #     ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, downlink_message)
                #     await self.send_internal_message(ext_msg)
                #     self.log(f'Sent message to transmitter!',level=logging.DEBUG)

                if(instrument == "VIIRS" or instrument == "OLI"): # TODO replace this hardcoding
                    self.tss_count+=1
                    self.log(f'TSS count: {self.tss_count}',level=logging.INFO)
                    data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time)
                    processed_data = self.compute_tss_obs_value(data)
                    self.sd = self.add_data_product(self.sd,lat,lon,obs_process_time,"tss",raw_data_filename,processed_data)
                    self.log(f'TSS measurement data successfully saved in on-board data-base.', level=logging.DEBUG)
                    self.updated.set()
                    updated_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_REASONING.value, self.updated)
                    await self.send_internal_message(updated_msg)
                    for item in self.sd:
                        if item["lat"] == lat and item["lon"] == lon and item["time"] == obs_process_time:
                            item["metadata"] = msg.metadata
                            value_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, item)
                            await self.send_internal_message(value_msg)
                    metadata = msg.get_metadata()
                    downlink_item = {
                        "lat": lat,
                        "lon": lon,
                        "time": metadata["time"],
                        #"product_type": metadata["measuring_instrument"]
                    }
                    self.downlink_items.append(downlink_item)
                    await self.save_observations()
                elif(instrument == "POSEIDON-3B Altimeter"): # TODO replace this hardcoding
                    data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time)
                    processed_data = self.compute_altimetry()
                    self.sd = self.add_data_product(self.sd,lat,lon,obs_process_time,"altimetry",raw_data_filename,processed_data)
                    self.log(f'Altimetry measurement data successfully saved in on-board data-base.', level=logging.DEBUG)
                    self.updated.set()
                    updated_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_REASONING.value, self.updated)
                    await self.send_internal_message(updated_msg)
                    for item in self.sd:
                        if item["lat"] == lat and item["lon"] == lon and item["time"] == obs_process_time:
                            item["metadata"] = msg.metadata
                            value_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, item)
                            await self.send_internal_message(value_msg)
                    metadata = msg.get_metadata()
                    downlink_item = {
                        "lat": lat,
                        "lon": lon,
                        "time": metadata["time"],
                        #"product_type": metadata["measuring_instrument"] TODO add back for ground station
                    }
                    self.downlink_items.append(downlink_item)
                    await self.save_observations()
                # elif(instrument == "Ground Sensor"):
                #     #data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time) TODO commenting this out to improve runtime
                #     metadata = msg.get_metadata()
                #     # prefix = self.parent_module.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
                #     # filename = prefix+str(lat)+"_"+str(lon)+"_"+str(obs_process_time)+"_raw.csv"
                #     # self.sd = self.add_data_product(self.sd,lat,lon,obs_process_time,metadata["measuring_instrument"],filename,None)
                #     downlink_item = {
                #         "lat": lat,
                #         "lon": lon,
                #         "time": metadata["time"],
                #         "product_type": metadata["measuring_instrument"]
                #     }
                #     self.downlink_items.append(downlink_item)
                #     await self.downlink_statistics()
                else:
                    self.log(f'Instrument not yet supported by science module!',level=logging.DEBUG)
                # release database lock and inform other processes that the database has been updated
                self.database_lock.release()

        except asyncio.CancelledError:
            return

    def store_raw_measurement(self,dataprod,lat,lon,obs_process_time):
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
        bda = b5 - b5/b4 + b4
        return bda

    def compute_tss_obs_value(self,b4):
        tss = 195.6 * b4
        return tss

    def compute_altimetry(self):
        return np.random.rand(100,100)

    def add_data_product(self,sd,lat,lon,time,product_type,filename,data):
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
        return sd

    async def downlink_statistics(self):
        coobs_count = 0
        tss_coords = []
        alt_coords = []
        tss_outlier_coords = []
        alt_outlier_coords = []
        coobs_coords = []
        for potential_alt_item in self.downlink_items:
            already_counted = False
            if(potential_alt_item["product_type"] == "POSEIDON-3B Altimeter"):
                for potential_tss_item in self.downlink_items:
                    if potential_tss_item["product_type"] == "OLI":
                        if potential_alt_item["lat"] == potential_tss_item["lat"] and potential_alt_item["lon"] == potential_tss_item["lon"] and not already_counted and self.check_altimetry_outlier(potential_tss_item):
                            coobs_count += 1
                            #self.log(f'Co-obs count: {coobs_count}',level=logging.INFO)
                            coobs_coords.append((potential_alt_item["lat"],potential_alt_item["lon"],potential_alt_item["time"]))
                            already_counted = True
        for potential_alt_item in self.downlink_items:
            if potential_alt_item["product_type"] == "POSEIDON-3B Altimeter":
                alt_coords.append((potential_alt_item["lat"],potential_alt_item["lon"],potential_alt_item["time"]))
                if self.check_altimetry_outlier(potential_alt_item):
                    alt_outlier_coords.append((potential_alt_item["lat"],potential_alt_item["lon"],potential_alt_item["time"]))
        for potential_tss_item in self.downlink_items:
            if potential_tss_item["product_type"] == "OLI":
                tss_coords.append((potential_tss_item["lat"],potential_tss_item["lon"],potential_tss_item["time"]))
                if self.check_altimetry_outlier(potential_tss_item):
                    tss_outlier_coords.append((potential_tss_item["lat"],potential_tss_item["lon"],potential_tss_item["time"]))
        if len(self.downlink_items) % 100 == 0:
            with open(self.parent_module.scenario_dir+'tss_obs.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in tss_coords:
                    csv_out.writerow(row)
            with open(self.parent_module.scenario_dir+'alt_obs.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in alt_coords:
                    csv_out.writerow(row)
            with open(self.parent_module.scenario_dir+'tss_outliers.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in tss_outlier_coords:
                    csv_out.writerow(row)
            with open(self.parent_module.scenario_dir+'alt_outliers.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in alt_outlier_coords:
                    csv_out.writerow(row)
            with open(self.parent_module.scenario_dir+'coobs_outliers.csv','w') as out:
                csv_out=csv.writer(out)
                csv_out.writerow(['lat','lon','time'])
                for row in coobs_coords:
                    csv_out.writerow(row)

    async def save_observations(self):
        all_coords = []
        outlier_coords = []
        parent_agent = self.get_top_module()
        sat_name = parent_agent.name
        for potential_outlier in self.downlink_items:
            if self.check_altimetry_outlier(potential_outlier):
                outlier_coords.append((potential_outlier["lat"],potential_outlier["lon"],potential_outlier["time"]))
        for item in self.downlink_items:
            all_coords.append((item["lat"],item["lon"],item["time"]))
        with open(self.parent_module.scenario_dir+sat_name+'_outliers.csv','w') as out:
            csv_out=csv.writer(out)
            csv_out.writerow(['lat','lon','time'])
            for row in outlier_coords:
                csv_out.writerow(row)
        with open(self.parent_module.scenario_dir+sat_name+'_all.csv','w') as out:
            csv_out=csv.writer(out)
            csv_out.writerow(['lat','lon','time'])
            for row in all_coords:
                csv_out.writerow(row)

    def check_altimetry_outlier(self,item):
        outlier = False
        flood_chance, lat, lon = self.get_flood_chance(item["lat"], item["lon"], self.parent_module.chl_points)
        if flood_chance > 0.90: # TODO remove this hardcode
            item["severity"] = flood_chance
            outlier = True
        return outlier

    def get_flood_chance(self, lat, lon, points):
        flood_chance = 0.0
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                flood_chance = points[i, 5]
                lat = points[i, 0]
                lon = points[i, 1]
                break
        return flood_chance, lat, lon




class SciencePredictiveModelModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__(ScienceSubmoduleTypes.SCIENCE_PREDICTIVE_MODEL.value, parent_module, submodules=[],
                         n_timed_coroutines=0)

    model_reqs = []
    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            dst_name = msg['dst']
            if dst_name != self.name:
                await self.put_message(msg)
            else:
                if msg['@type'] == 'PRINT':
                    content = msg['content']
                    #self.log(content)
                if msg['@type'] == 'MODEL_REQ':
                    self.model_reqs.append(msg['content'])
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
            ## Internal coroutines
            send_meas_req = asyncio.create_task(self.send_meas_req())
            send_meas_req.set_name (f'{self.name}_send_meas_req')
            coroutines.append(send_meas_req)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    done_name = coroutine.get_name()

            # cancel all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine.cancel()
                await subroutine
        
        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    async def send_meas_req(self):
        forecast_data = np.genfromtxt(self.parent_module.scenario_dir+'ForecastWarnings-all.csv', delimiter=',')
        for row in forecast_data:
            measurement_request = MeasurementRequest("tss", row[2], row[3], 1.0, {})
            req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
            ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, measurement_request)
            await self.send_internal_message(req_msg)
            await self.send_internal_message(ext_msg)
            self.log(f'Sent message from predictive model!',level=logging.INFO)

class ScienceReasoningModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__(ScienceSubmoduleTypes.SCIENCE_REASONING.value, parent_module, submodules=[],
                         n_timed_coroutines=0)

    model_results = []
    async def activate(self):
        await super().activate()
        self.updated_queue = asyncio.Queue()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module == ScienceSubmoduleTypes.SCIENCE_PREDICTIVE_MODEL.value):
                self.model_results.append(msg.content)
            elif(msg.src_module == ScienceSubmoduleTypes.ONBOARD_PROCESSING.value):
                await self.updated_queue.put(msg)
            else:
                self.log(f'Unsupported message for this module.')
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
            ## Internal coroutines
            check_sd = asyncio.create_task(self.check_sd())
            check_sd.set_name (f'{self.name}_check_sd')
            coroutines.append(check_sd)

            # wait for the first coroutine to complete
            _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
            done_name = None
            for coroutine in coroutines:
                if coroutine not in pending:
                    done_name = coroutine.get_name()

            # cancel all other coroutine tasks
            self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
            for subroutine in pending:
                subroutine.cancel()
                await subroutine
        
        except asyncio.CancelledError:
            if len(coroutines) > 0:
                for coroutine in coroutines:
                    coroutine : asyncio.Task
                    if not coroutine.done():
                        coroutine.cancel()
                        await coroutine

    def get_mean_sd(self, lat, lon, points):
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

    def get_flood_chance(self, lat, lon, points):
        flood_chance = 0.0
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                flood_chance = points[i, 5]
                lat = points[i, 0]
                lon = points[i, 1]
                break
        return flood_chance, lat, lon

    async def check_sd(self):
        try:
            while True:
                msg = await self.updated_queue.get()
                outliers = []
                for item in self.sd:
                    if(item["product_type"] == "tss"):
                        self.log(f'TSS data not checked for outliers.',level=logging.DEBUG)
                        #outlier, outlier_data = self.check_tss_outliers(item)
                        #if outlier is True:
                        #    outliers.append(outlier_data)
                    elif(item["product_type"] == "altimetry"):
                        outlier, outlier_data = self.check_altimetry_outliers(item)
                        if outlier is True:
                            outliers.append(outlier_data)
                    else:
                        self.log(f'Item in science database unsupported by science processing module.',level=logging.DEBUG)
                for outlier in outliers:
                    self.log(f'Outliers: {outlier}',level=logging.INFO)
                    msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, outlier)
                    await self.send_internal_message(msg)
        except asyncio.CancelledError:
            return
    
    def check_tss_outliers(self,item):
        outlier = False
        outlier_data = None
        if(item["checked"] is False):
            mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], self.parent_module.chl_points)
            pixel_value = self.get_pixel_value_from_image(item,lat,lon,30) # 30 meters is landsat resolution
            if mean > 30000: # TODO remove this hardcode
                item["severity"] = (pixel_value-mean) / stddev
                outlier_data = item
                self.log(f'TSS outlier detected at {lat}, {lon}!',level=logging.INFO)
            else:
                self.log(f'No TSS outlier detected at {lat}, {lon}',level=logging.INFO)
            item["checked"] = True
        return outlier, outlier_data

    def check_altimetry_outliers(self,item):
        outlier = False
        outlier_data = None
        if(item["checked"] is False):
            flood_chance, lat, lon = self.get_flood_chance(item["lat"], item["lon"], self.parent_module.chl_points)
            if flood_chance > 0.90: # TODO remove this hardcode
                item["severity"] = flood_chance
                outlier = True
                outlier_data = item
                self.log(f'Flood detected at {lat}, {lon}!',level=logging.INFO)
            else:
                self.log(f'No flood detected at {lat}, {lon}',level=logging.INFO)
            item["checked"] = True
        return outlier, outlier_data

    def get_pixel_value_from_image(self,image, lat, lon, resolution):
        topleftlat = image["lat"]
        topleftlon = image["lon"]
        latdiff = lat-topleftlat
        londiff = lon-topleftlon
        row = (latdiff*111139)//resolution # latitude to meters
        col = (londiff*111139)//resolution
        data = pd.read_csv(image["filepath"])
        pixel_values = data.values
        pixel_value = pixel_values[int(row),int(col)]
        return pixel_value
