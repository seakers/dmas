import asyncio
import json
import os
import pandas as pd
import numpy as np
import csv
from modules import Module

def get_data_product(sd,lat,lon,time,product_type):
        for item in sd:
            if item["lat"] == lat and item["lon"] == lon and item["time"] == time and item["product_type"]==product_type:
                if(item["filepath"].lower().endswith('.csv')):
                    df = pd.read_csv(item["filepath"])
                    return df

class ScienceModule(Module):
    def __init__(self, name, parent_module, scenario_dir, submodules=[], n_timed_coroutines=2) -> None:
        self.scenario_dir = scenario_dir
        super().__init__(name, parent_module, submodules, n_timed_coroutines)
        self.data_products = []
        self.load_data_products()
        self.submodules = [
            ScienceValueModule(self,self.data_products),
            SciencePredictiveModelModule(self,self.data_products),
            OnboardProcessingModule(self,self.data_products),
            ScienceReasoningModule(self,self.data_products)
        ]

    def load_data_products(self):
        for file in os.listdir(self.scenario_dir):
            if(file.lower().endswith('.txt')):
                with open(file) as headerfile:
                    data_product_dict = json.load(headerfile)
                    self.data_products.append(data_product_dict)

    def get_data_product(self,lat,lon,time,product_type):
        for item in self.data_products:
            if item["lat"] == lat and item["lon"] == lon and item["time"] == time and item["product_type"]==product_type:
                if(item["filepath"].lower().endswith('.csv')):
                    df = pd.read_csv(item["filepath"])
                    self.log("Found data product!")
                    return df
                else:
                    self.log("Found data product but file type not supported")
            else:
                self.log("Could not find data product")

    def add_data_product(self,lat,lon,time,product_type,filepath,data):
        data_product_dict = dict()
        data_product_dict["lat"] = lat
        data_product_dict["lon"] = lon
        data_product_dict["time"] = time
        data_product_dict["product_type"] = product_type
        data_product_dict["filepath"] = filepath
        pd.write_csv(filepath,data)
        self.data_products.append(data_product_dict)
        with open('dataprod'+lat+lon+time+product_type+'.txt') as datafile:
            datafile.write(json.dumps(data_product_dict))

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
                    self.log(content)                
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            while True:
                await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return


class ScienceValueModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__('Science Value Module', parent_module, submodules=[],
                         n_timed_coroutines=0)

    prop_meas_obs_metrics = []

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
                    self.log(content)
                if msg['@type'] == 'PROP_MEAS_OBS_METRIC':
                    self.prop_meas_obs_metrics.append(msg)
                if msg['@type'] == 'ALGAL BLOOM':
                    event = msg['content']
                    self.broadcast_meas_req(event,event["severity"])
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running Science Value module coroutines")
        compute_science_value = asyncio.create_task(self.compute_science_value())
        await compute_science_value
        compute_science_value.cancel()
        self.log("Completed science value module coroutines")


    async def broadcast_meas_req(self, param_msg, result):
        msg_dict = dict()
        msg_dict['src'] = self.name
        msg_dict['dst'] = 'Planner'
        msg_dict['@type'] = 'MEAS_REQ'
        msg_dict['content'] = param_msg
        msg_dict['result'] = result
        msg_json = json.dumps(msg_dict)
        await self.publisher.send_json(msg_json)

    async def compute_science_value(self):
        try:
            while True:
                for i in range(len(self.prop_meas_obs_metrics)):
                    if(self.prop_meas_obs_metrics[i]['result'] == None):
                        obs = self.prop_meas_obs_metrics[i]
                        dataprod = get_data_product(self.sd,obs["lat"],obs["lon"],obs["time"],obs["product_type"])
                        result = 1.0 # CHANGE THIS TO ACTUAL CALC
                        self.announce_computed_science_value(self.prop_meas_obs_metrics[i],result)
                        self.log("Computed science value")
                    else:
                        self.prop_meas_obs_metrics.pop(i)
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return




class OnboardProcessingModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__('Onboard Processing Module', parent_module, submodules=[],
                         n_timed_coroutines=0)

    meas_results = []
    data_processing_requests = []
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
                    self.log(content)
                if msg['@type'] == 'MEAS_RESULT':
                    self.meas_results.append(msg['content'])
                if msg['@type'] == 'DATA_PROCESSING_REQUEST':
                    self.data_processing_requests.append(msg['content'])
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running Onboard Processing module coroutines")
        process_meas_results = asyncio.create_task(self.process_meas_results())
        await process_meas_results
        process_meas_results.cancel()
        self.log("Completed Onboard Processing module coroutines")

    async def process_meas_results(self):
        try:
            while True:
                for i in range(len(self.meas_results)):
                    if(self.meas_results[i]["level"] == 0):
                        data = self.meas_results[i]
                        processed_data = self.compute_chlorophyll_obs_value(data)
                        self.sd = self.add_data_product(self.sd,data["lat"],data["lon"],data["time"],"chlorophyll-a",data["filepath"]+"_chla",processed_data)
                        self.meas_results.pop(i)
                        self.log("Computed science value")
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

    def compute_chlorophyll_obs_value(dataprod):
        b5 = dataprod["B5"]
        b4 = dataprod["B4"]
        bda = b5 - b5/b4 + b4
        return bda

    def add_data_product(sd,lat,lon,time,product_type,filepath,data):
        data_product_dict = dict()
        data_product_dict["lat"] = lat
        data_product_dict["lon"] = lon
        data_product_dict["time"] = time
        data_product_dict["product_type"] = product_type
        data_product_dict["filepath"] = filepath
        pd.write_csv(filepath,data)
        sd.append(data_product_dict)
        with open('dataprod'+lat+lon+time+product_type+'.txt') as datafile:
            datafile.write(json.dumps(data_product_dict))
        return sd



class SciencePredictiveModelModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__('Science Predictive Model Module', parent_module, submodules=[],
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
                    self.log(content)
                if msg['@type'] == 'MODEL_REQ':
                    self.model_reqs.append(msg['content'])
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        try:
            while True:
                await self.sim_wait(1e6, module_name=self.name)
        except asyncio.CancelledError:
            return

class ScienceReasoningModule(Module):
    def __init__(self, parent_module, sd) -> None:
        self.sd = sd
        super().__init__('Science Reasoning Module', parent_module, submodules=[],
                         n_timed_coroutines=0)

    model_results = []
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
                    self.log(content)
                if msg['@type'] == 'MODEL_RES':
                    self.model_results.append(msg['content'])
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running Science Reasoning module coroutines")
        check_chlorophyll_outliers = asyncio.create_task(self.check_chlorophyll_outliers(self.sd))
        await check_chlorophyll_outliers
        check_chlorophyll_outliers.cancel()
        self.log("Completed Science Reasoning module coroutines")

    def get_mean_sd(self, lat, lon, points):
        mean = 0.0
        sd = 0.0
        for i in range(len(points[:, 0])):
            if (float(lat)-points[i, 1] < 0.01) and (float(lon) - points[i, 0] < 0.01):
                mean = points[i, 2]
                sd = points[i, 3]
                lat = points[i, 1]
                lon = points[i, 0]
                break
        return mean, sd, lat, lon

    async def check_chlorophyll_outliers(self,sd):
        try:
            while True:
                points = np.zeros(shape=(2000, 4))
                chlorophyll_outliers = []
                with open('/home/ben/repos/dmaspy/scenarios/sim_test/chlorophyll_baseline.csv') as csvfile:
                    reader = csv.reader(csvfile)
                    count = 0
                    for row in reader:
                        if count == 0:
                            count = 1
                            continue
                        points[count-1,:] = [row[0], row[1], row[2], row[3]]
                        count = count + 1
                for item in sd:
                    mean, stddev, lat, lon = self.get_mean_sd(item["lat"], item["lon"], points)
                    pixel_value = self.get_pixel_value_from_image(item,lat,lon,30)
                    if pixel_value > mean+stddev:
                        item["severity"] = (pixel_value-mean) / stddev
                        chlorophyll_outliers.append(item)
                for outlier in chlorophyll_outliers:
                    msg = dict()
                    msg['src'] = self.name
                    msg['dst'] = 'Science Value Module'
                    msg['@type'] = 'ALGAL BLOOM'
                    msg['content'] = outlier
                    await self.parent_module.send_internal_message(msg)
                await self.sim_wait(1e6)
        except asyncio.CancelledError:
            return

    def get_pixel_value_from_image(self,image, lat, lon, resolution):
        topleftlat = image["lat"]
        topleftlon = image["lon"]
        latdiff = lat-topleftlat
        londiff = lon-topleftlon
        row = (latdiff*111139)/resolution
        col = (londiff*111139)/resolution
        data = pd.read_csv(image["filepath"])
        pixel_value = data.values[row][col]
        return pixel_value
