import asyncio
import json
import os
import csv
import numpy as np
from modules import Module
from messages import *
from neo4j import GraphDatabase

class PlanningModule(Module):
    def __init__(self, name, parent_module, scenario_dir, submodules=[], n_timed_coroutines=3) -> None:
        self.scenario_dir = scenario_dir
        super().__init__(name, parent_module, submodules, n_timed_coroutines)
        self.submodules = [
            InstrumentCapabilityModule(self),
            ObservationPlanningModule(self),
            PredictiveModelsModule(self),
            MeasurementPerformanceModule(self)
        ]

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
                await self.sim_wait(1.0, module_name=self.name)
        except asyncio.CancelledError:
            return


class InstrumentCapabilityModule(Module):
    def __init__(self, parent_module) -> None:
        self.to_be_sent = False
        self.msg_content = None
        self.request_msg = None
        super().__init__('Instrument Capability Module', parent_module, submodules=[],
                         n_timed_coroutines=2)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            self.log(f'Internal message handler in instrument capability module')
            self.request_msg = msg.content
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running instrument capability module coroutines")
        check_database = asyncio.create_task(self.check_database())
        broadcast_meas_req = asyncio.create_task(self.broadcast_meas_req())
        await check_database
        await broadcast_meas_req
        check_database.cancel()
        broadcast_meas_req.cancel()
        self.log("Finished instrument capability module coroutines")


    async def broadcast_meas_req(self):
        try:
            while True:
                if self.to_be_sent:
                    self.log(f'In self to be sent')
                    msg = InternalMessage(self.name, "Observation Planning Module", self.msg_content)
                    await self.parent_module.send_internal_message(msg)
                    self.to_be_sent = False
                # msg_dict = dict()
                # msg_dict['src'] = self.name
                # msg_dict['dst'] = 'Planner'
                # msg_dict['@type'] = 'MEAS_REQ'
                # msg_dict['content'] = param_msg
                # msg_dict['result'] = result
                # msg_json = json.dumps(msg_dict)
                # await self.publisher.send_json(msg_json)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

    async def check_database(self):
        try:
            while True:
                if(self.request_msg is not None):
                    self.queryGraphDatabase("bolt://localhost:7687", "neo4j", "test", "OLI")
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

    def queryGraphDatabase(self, uri, user, password, sc_name):
        driver = GraphDatabase.driver(uri, auth=(user, password))
        self.print_observers(driver,sc_name)
        driver.close()

    def print_observers(self,driver,sc_name):
        with driver.session() as session:
            product = "None"
            self.log(f'In print observers')
            self.log(self.request_msg.content["product_type"])
            if(self.request_msg.content["product_type"] == "chlorophyll-a"):
                product = "Ocean chlorophyll concentration"
            observers = session.read_transaction(self.get_observers, title=product)
            for observer in observers:
                if(observer.get("name") == sc_name):
                    self.log(f'Matching instrument!')
                    self.to_be_sent = True
                    self.request_msg.content["Measurable status"] = "Able to be measured"
                    self.msg_content = self.request_msg.content

    @staticmethod
    def get_observers(tx, title): # (1)
        result = tx.run("""
            MATCH (p:Sensor)-[r:OBSERVES]->(:ObservableProperty {name: $title})
            RETURN p
        """, title=title)

        # Access the `p` value from each record
        return [ record["p"] for record in result ]

class ObservationPlanningModule(Module):
    def __init__(self, parent_module) -> None:
        self.task_list = []
        self.plan = []
        super().__init__('Observation Planning Module', parent_module, submodules=[],
                         n_timed_coroutines=1)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module=="Instrument Capability Module"):
                self.task_list.append(msg.content)
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running observation planning module coroutines")
        create_plan = asyncio.create_task(self.create_plan())
        await create_plan
        create_plan.cancel()
        self.log("Finished observation planning module coroutines")


    async def create_plan(self):
        try:
            while True:
                if(len(self.task_list) > 0):
                    # replace this with an actual planner!
                    for i in range(len(self.task_list)):
                        self.plan.append(self.task_list[i])
                    plan_msg = InternalMessage(self.name, "Planner Predictive Models Module", self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class PredictiveModelsModule(Module):
    def __init__(self, parent_module) -> None:
        self.agent_state = None
        self.plan = None
        super().__init__('Planner Predictive Models Module', parent_module, submodules=[],
                         n_timed_coroutines=1)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            self.plan = msg.content
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running Planner Predictive Models Module coroutines")
        predict_state = asyncio.create_task(self.predict_state())
        await predict_state
        predict_state.cancel()
        self.log("Finished Planner Predictive Models Module coroutines")


    async def predict_state(self):
        try:
            while True:
                if(self.plan is not None):
                    plan_msg = InternalMessage(self.name, "Measurement Performance Module", self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class MeasurementPerformanceModule(Module):
    def __init__(self, parent_module) -> None:
        self.plan = None
        super().__init__('Measurement Performance Module', parent_module, submodules=[],
                         n_timed_coroutines=1)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            self.plan = msg.content
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running Measurement Performance Module coroutines")
        evaluate_performance = asyncio.create_task(self.evaluate_performance())
        await evaluate_performance
        evaluate_performance.cancel()
        self.log("Finished Measurement Performance Module coroutines")


    async def evaluate_performance(self):
        try:
            while True:
                if(self.plan is not None):
                    for i in range(len(self.plan)):
                        event = self.plan[i]
                        self.log(event)
                        observation_time = 20.0
                        delta = observation_time - float(event["time"])
                        lagfunc = -0.08182 * np.log(delta)+0.63182
                        event["meas_perf_value"] = lagfunc
                        self.plan[i] = event
                    plan_msg = InternalMessage(self.name, "Observation Planning Module", self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return