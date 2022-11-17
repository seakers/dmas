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
    def __init__(self, parent_agent : Module, scenario_dir : str) -> None:
        super().__init__(AgentModuleTypes.SCIENCE_MODULE.value, parent_agent, [], 0)

        self.scenario_dir = scenario_dir

        data_products = self.load_data_products()        

        self.submodules = [
            OnboardProcessingModule(self, data_products),            
            ScienceReasoningModule(self, data_products),
            ScienceValueModule(self, data_products)
            # SciencePredictiveModelModule(self,self.data_products),           
        ]

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

                else:
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

        except asyncio.CancelledError:
            return

       # def get_data_product(self,lat,lon,time,product_type):
    #     for item in self.data_products:
    #         if item["lat"] == lat and item["lon"] == lon and item["time"] == time and item["product_type"]==product_type:
    #             if(item["filepath"].lower().endswith('.csv')):
    #                 df = pd.read_csv(item["filepath"])
    #                 self.log("Found data product!")
    #                 return df
    #             else:
    #                 self.log("Found data product but file type not supported")
    #         else:
    #             self.log("Could not find data product")

    # def add_data_product(self,lat,lon,time,product_type,filepath,data):
    #     data_product_dict = dict()
    #     data_product_dict["lat"] = lat
    #     data_product_dict["lon"] = lon
    #     data_product_dict["time"] = time
    #     data_product_dict["product_type"] = product_type
    #     data_product_dict["filepath"] = filepath
    #     pd.write_csv(filepath,data)
    #     self.data_products.append(data_product_dict)
    #     with open('./scenarios/sim_test/results/sd/dataprod'+lat+lon+time+product_type+'.txt') as datafile:
    #         datafile.write(json.dumps(data_product_dict))

# class OnboardProcessingModule(Module):
#     def __init__(self, parent_module : Module, sd : list) -> None:
#         self.sd : list = sd
#         super().__init__('Onboard Processing Module', parent_module, submodules=[],
#                          n_timed_coroutines=0)

#         self.meas_results = []
#         self.data_processing_requests = []

#     async def activate(self):
#         await super().activate()

#         # incoming message queues
#         self.incoming_results = asyncio.Queue()

#         # events
#         self.updated = asyncio.Event()
#         self.database_lock = asyncio.Lock()


#     async def internal_message_handler(self, msg):
#         """
#         Handles message intended for this module and performs actions accordingly.
#         """
#         try:
#             if isinstance(msg, DataMessage):
#                 # polling-driven
#                 # self.meas_results.append(msg)

#                 # previous-messaging-standard
#                 # dst_name = msg['dst']
#                 # if dst_name != self.name:
#                 #     await self.put_message(msg)
#                 # else:
#                 #     if msg['@type'] == 'PRINT':
#                 #         content = msg['content']
#                 #         self.log(content)
#                 #     if msg.type == 'MEAS_RESULT':
#                 #         self.log(f'Received measurement result!')
#                 #         self.meas_results.append(msg['content'])
#                 #     if msg['@type'] == 'DATA_PROCESSING_REQUEST':
#                 #         self.data_processing_requests.append(msg['content'])

#                 # event-driven
#                 self.log(f'Received new observation data! Processing...')            
#                 await self.incoming_results.put(msg)

#             elif isinstance(msg, RequestMessage) and isinstance(msg.get_request(), InformationRequest):
#                 # TODO add support for information requests 
#                 self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')            

#             elif isinstance(msg, RequestMessage) and isinstance(msg.get_request(), DataProcessingRequest):
#                 # TODO add support for data processing requests 
#                 self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')            

#             else:
#                 self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')            
            
#         except asyncio.CancelledError:
#             return

#     async def coroutines(self):
#         try:
#             coroutines = []

#             # start result-processing routine
#             processs_incoming_results = asyncio.create_task(self.processs_incoming_results())
#             processs_incoming_results.set_name('processs_incoming_results')
#             coroutines.append(processs_incoming_results)

#             # TODO add information request and data processing routines

#             # wait for the first coroutine to complete
#             _, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
            
#             done_name = None
#             for coroutine in coroutines:
#                 if coroutine not in pending:
#                     coroutine : asyncio.Task
#                     done_name = coroutine.get_name()

#             # cancell all other coroutine tasks
#             self.log(f'{done_name} Coroutine ended. Terminating all other coroutines...', level=logging.INFO)
#             for subroutine in pending:
#                 subroutine : asyncio.Task
#                 subroutine.cancel()
#                 await subroutine
        
#         except asyncio.CancelledError:
#             return

#         finally:
#             self.log("Stopped processing incoming measurement results.")

#     async def processs_incoming_results(self):
#         try:
#             self.log("Processing any incoming measurement results...")
#             acquired = None
#             while True:
#                 # polling-driven
#                 # for i in range(len(self.meas_results)):
#                     # meas_result = self.meas_results[i].content
#                     # lat = meas_result.lat
#                     # lon = meas_result.lon
#                     # self.log(f'Received measurement result from ({lat}°, {lon}°)!')
#                     # b4,b5,prefix,stored_data_filepath = self.store_measurement(meas_result.obs)
#                     # processed_data = self.compute_chlorophyll_obs_value(b4,b5)
#                     # self.sd = self.add_data_product(self.sd,lat,lon,0.01,"chlorophyll-a",prefix+"chla_"+stored_data_filepath,processed_data)
#                     # self.meas_results.pop(i)
#                     # # if(self.meas_results[i]["level"] == 0):
#                     # #     data = self.meas_results[i]
#                     # #     processed_data = self.compute_chlorophyll_obs_value(data)
#                     # #     self.sd = self.add_data_product(self.sd,data["lat"],data["lon"],data["time"],"chlorophyll-a",data["filepath"]+"_chla",processed_data)
#                     # #     self.meas_results.pop(i)
#                     # #     self.log("Computed science value")
#                 # await self.sim_wait(1.0)

#                 # event-driven
#                 # reset updat event
#                 if self.updated.is_set():
#                    self.updated.clear() 

#                 # wait for next measurement result to come in
#                 msg : DataMessage = await self.incoming_results.get()
#                 acquired = await self.database_lock.acquire()

#                 # unpackage result
#                 obs_str = msg.get_data()
#                 lat, lon = msg.get_target()

#                 self.log(f'Received measurement result from ({lat}°, {lon}°)!')

#                 # process result
#                 b4,b5,prefix,stored_data_filepath = self.store_measurement(obs_str)
#                 processed_data = self.compute_chlorophyll_obs_value(b4,b5)
#                 self.sd = self.add_data_product(self.sd,lat,lon,0.01,"chlorophyll-a",prefix+"chla_"+stored_data_filepath,processed_data)

#                 # release database lock and inform other processes that the database has been updated
#                 self.log(f'Measurement data successfully saved in on-board data-base.')
#                 self.database_lock.release()
#                 self.updated.set()

#         except asyncio.CancelledError:
#             if acquired:
#                 self.database_lock.release()
#             self.log("Incoming measurement processing interrupted!")

#         finally:
#             self.log("Stopped processing incoming measurement results.")
            
#     def store_measurement(self,dataprod : str):
#         # decode string into an image
#         im = Image.open(BytesIO(base64.b64decode(dataprod)))
        
#         img_np = np.array(im)
#         b5 = img_np[:,:,0]
#         b4 = img_np[:,:,1]
#         img_np = np.delete(img_np,3,2)

#         # from https://stackoverflow.com/questions/67831382/obtaining-rgb-data-from-image-and-writing-it-to-csv-file-with-the-corresponding
#         xy_coords = np.flip(np.column_stack(np.where(np.all(img_np >= 0, axis=2))), axis=1)
#         rgb = np.reshape(img_np, (np.prod(img_np.shape[:2]), 3))

#         # Add pixel numbers in front
#         pixel_numbers = np.expand_dims(np.arange(1, xy_coords.shape[0] + 1), axis=1)
#         value = np.hstack([pixel_numbers, xy_coords, rgb])

#         # Properly save as CSV
#         prefix = "./scenarios/sim_test/results/sd/"
#         np.savetxt(prefix+"outputdata.csv", value, delimiter='\t', fmt='%4d')
#         return b4, b5, prefix, "outputdata.csv"

#     def compute_chlorophyll_obs_value(self,b4,b5):
#         bda = b5 - b5/b4 + b4
#         return bda

#     def add_data_product(self,sd,lat,lon,time,product_type,filepath,data):
#         data_product_dict = dict()
#         data_product_dict["lat"] = lat
#         data_product_dict["lon"] = lon
#         data_product_dict["time"] = time
#         data_product_dict["product_type"] = product_type
#         data_product_dict["filepath"] = filepath
#         pd.DataFrame(data).to_csv(filepath,index=False,header=False)
#         sd.append(data_product_dict)
#         with open("./scenarios/sim_test/results/sd/dataprod"+"_"+str(lat)+"_"+str(lon)+"_"+str(time)+"_"+product_type+".txt", mode="wt") as datafile:
#             datafile.write(json.dumps(data_product_dict))
#         return sd


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

                science_value = self.compute_science_value(lat, lon, obs)                

                measurement_request = MeasurementRequest("tss", lat, lon, science_value)

                req_msg = InternalMessage(self.name, AgentModuleTypes.PLANNING_MODULE.value, measurement_request)
                ext_msg = InternalMessage(self.name, ComponentNames.TRANSMITTER.value, measurement_request)
                await self.send_internal_message(req_msg)
                await self.send_internal_message(ext_msg)
                self.log(f'Sent message to transmitter!',level=logging.INFO)

        except asyncio.CancelledError:
            return

    async def meas_handler(self):
        try:
            while True:
                msg : DataMessage = await self.meas_msg_queue.get()
                lat = msg.content["lat"]
                lon = msg.content["lon"]
                obs = msg.content

                science_value = self.compute_science_value(lat, lon, obs)                

                self.log(f'Received measurement with value {science_value}!',level=logging.INFO)
                self.science_value_sum = self.science_value_sum + science_value
                self.log(f'Sum of science values: {self.science_value_sum}',level=logging.INFO)
                self.log(f'Sum of science values: {self.science_value_sum}', logger_type=LoggerTypes.RESULTS, level=logging.INFO)

        except asyncio.CancelledError:
            return

    def compute_science_value(self, lat, lon, obs):
        self.log(f'Computing science value...', level=logging.INFO)
        
        points = np.zeros(shape=(2000, 5))

        with open(self.parent_module.scenario_dir+'chlorophyll_baseline.csv') as csvfile:
            reader = csv.reader(csvfile)
            count = 0
            for row in reader:
                if count == 0:
                    count = 1
                    continue
                points[count-1,:] = [row[0], row[1], row[2], row[3], row[4]]
                count = count + 1

        science_val = self.get_pop(lat, lon, points)
        if(self.check_tss_outlier(obs)):
            science_val = science_val * 10
            self.log(f'Computed bonus science value: {science_val}', level=logging.INFO)
        else:
            self.log(f'Computed normal science value: {science_val}', level=logging.INFO)
        return science_val*self.meas_perf()

    def get_pop(self, lat, lon, points):
        pop = 0.0
        for i in range(len(points[:, 0])):
            if (abs(float(lat)-points[i, 0]) < 0.01) and (abs(float(lon) - points[i, 1]) < 0.01):
                pop = points[i,4]
                break
        return pop

    def check_tss_outlier(self,item):
        outlier = False
        points = np.zeros(shape=(2000, 5))
        with open(self.parent_module.scenario_dir+'chlorophyll_baseline.csv') as csvfile:
            reader = csv.reader(csvfile)
            count = 0
            for row in reader:
                if count == 0:
                    count = 1
                    continue
                points[count-1,:] = [row[0], row[1], row[2], row[3], row[4]]
                count = count + 1
        mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], points)
        if mean > 30000: # TODO remove this hardcode
            self.log(f'TSS outlier measured at {lat}, {lon}!',level=logging.INFO)
            outlier = True
        else:
            self.log(f'No TSS outlier measured at {lat}, {lon}',level=logging.INFO)
        item["checked"] = True
        return outlier

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
        if(instrument=="VIIRS"):
            x = parent_agent.payload[parent_agent.name]["snr"]
            y = parent_agent.payload[parent_agent.name]["spatial_res"]
            z = parent_agent.payload[parent_agent.name]["spectral_res"]
            meas = a*x-b*y-c*np.log10(z)+d
            spatial = a1*pow(np.e,(b1*y+c1))
            perf = 0.75*meas+0.25*spatial # modify to include temporal res at some point
        else:
            perf = 1
        self.log(f'Measurement performance: {perf}',level=logging.INFO)
        return perf


class OnboardProcessingModule(Module):
    def __init__(self, parent_module : Module, sd : list) -> None:
        self.sd : list = sd
        super().__init__(ScienceSubmoduleTypes.ONBOARD_PROCESSING.value, parent_module, submodules=[],
                         n_timed_coroutines=0)

        self.meas_results = []
        self.data_processing_requests = []

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
                self.log(f'Received new observation data! Processing...', level=logging.INFO)            
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

                self.log(f'Received measurement result from ({lat}°, {lon}°)!', level=logging.INFO)

                # process result
                obs_process_time = self.get_current_time()

                parent_agent = self.get_top_module()
                instrument = parent_agent.payload[parent_agent.name]["name"]
                self.log(f'Instrument: {instrument}',level=logging.DEBUG)
                if(instrument == "VIIRS"): # TODO replace this hardcoding
                    data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time)
                    processed_data = self.compute_tss_obs_value(data)
                    self.sd = self.add_data_product(self.sd,lat,lon,obs_process_time,"tss",raw_data_filename,processed_data)
                    self.log(f'TSS measurement data successfully saved in on-board data-base.', level=logging.INFO)
                elif(instrument == "POSEIDON-3B Altimeter"): # TODO replace this hardcoding
                    data,raw_data_filename = self.store_raw_measurement(obs_str,lat,lon,obs_process_time)
                    processed_data = self.compute_altimetry()
                    self.sd = self.add_data_product(self.sd,lat,lon,obs_process_time,"altimetry",raw_data_filename,processed_data)
                    self.log(f'Altimetry measurement data successfully saved in on-board data-base.', level=logging.INFO)
                else:
                    self.log(f'Instrument not yet supported by science module!',level=logging.INFO)
                # release database lock and inform other processes that the database has been updated
                self.database_lock.release()
                self.updated.set()
                updated_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_REASONING.value, self.updated)
                await self.send_internal_message(updated_msg)
                for item in self.sd:
                    if item["lat"] == lat and item["lon"] == lon and item["time"] == obs_process_time:
                        value_msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, item)
                        await self.send_internal_message(value_msg)
        except asyncio.CancelledError:
            return

    def store_raw_measurement(self,dataprod,lat,lon,obs_process_time):
        im = PIL.Image.open(BytesIO(base64.b64decode(dataprod)))

        img_np = np.array(im)
        data = img_np[:,:,0]
        img_np = np.delete(img_np,3,2)
        # from https://stackoverflow.com/questions/67831382/obtaining-rgb-data-from-image-and-writing-it-to-csv-file-with-the-corresponding
        xy_coords = np.flip(np.column_stack(np.where(np.all(img_np >= 0, axis=2))), axis=1)
        rgb = np.reshape(img_np, (np.prod(img_np.shape[:2]), 3))

        # Add pixel numbers in front
        pixel_numbers = np.expand_dims(np.arange(1, xy_coords.shape[0] + 1), axis=1)
        value = np.hstack([pixel_numbers, xy_coords, rgb])

        # Properly save as CSV
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
        pd.DataFrame(data).to_csv(data_product_dict["filepath"],index=False,header=False)
        sd.append(data_product_dict)
        prefix = self.parent_module.scenario_dir+"results/"+str(self.parent_module.parent_module.name)+"/sd/"
        filename = prefix+"dataprod"+"_"+str(lat)+"_"+str(lon)+"_"+str(time)+"_"+product_type+".txt"
        with open(filename, mode="wt") as datafile:
            datafile.write(json.dumps(data_product_dict))
        return sd




class SciencePredictiveModelModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__(ScienceSubmoduleTypes.PREDICTIVE_MODELS.value, parent_module, submodules=[],
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
        try:
            while True:
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

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

    

    async def check_sd(self):
        try:
            while True:
                msg = await self.updated_queue.get()
                outliers = []
                for item in self.sd:
                    if(item["product_type"] == "tss"):
                        outlier, outlier_data = self.check_tss_outliers(item)
                        if outlier is True:
                            outliers.append(outlier_data)
                    elif(item["product_type"] == "altimetry"):
                        outlier, outlier_data = self.check_altimetry_outliers(item)
                        if outlier is True:
                            outliers.append(outlier_data)
                    else:
                        self.log(f'Item in science database unsupported by science processing module.',level=logging.INFO)
                for outlier in outliers:
                    self.log(f'Outliers: {outlier}',level=logging.INFO)
                    msg = InternalMessage(self.name, ScienceSubmoduleTypes.SCIENCE_VALUE.value, outlier)
                    await self.send_internal_message(msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return
    
    def check_tss_outliers(self,item):
        outlier = False
        outlier_data = None
        if(item["checked"] is False):
            points = np.zeros(shape=(2000, 5))
            with open(self.parent_module.scenario_dir+'chlorophyll_baseline.csv') as csvfile:
                reader = csv.reader(csvfile)
                count = 0
                for row in reader:
                    if count == 0:
                        count = 1
                        continue
                    points[count-1,:] = [row[0], row[1], row[2], row[3], row[4]]
                    count = count + 1
            mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], points)
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
            data = np.genfromtxt(item["filepath"], delimiter=',')
            lat = item["lat"]
            lon = item["lon"]
            if(data[0,0] > 0.5):
                outlier = True
                outlier_data = item
                self.log(f'Altimetry outlier detected at {lat}, {lon}!',level=logging.INFO)
            else:
                self.log(f'No altimetry outlier detected at {lat}, {lon}!',level=logging.INFO)
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
