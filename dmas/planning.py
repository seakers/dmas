import asyncio
import json
import os
import csv
import numpy as np
from modules import Module
from messages import *
from neo4j import GraphDatabase
from utils import PlanningModuleSubmoduleTypes

class PlanningModule(Module):
    def __init__(self, parent_agent : Module, scenario_dir : str) -> None:
        super().__init__(AgentModuleTypes.PLANNING_MODULE.value, parent_agent, [], 3)
        self.scenario_dir = scenario_dir
        self.submodules = [
            InstrumentCapabilityModule(self),
            ObservationPlanningModule(self),
            PredictiveModelsModule(self),
            MeasurementPerformanceModule(self)
        ]

class InstrumentCapabilityModule(Module):
    def __init__(self, parent_module) -> None:
        self.to_be_sent = False
        self.msg_content = None
        self.request_msg = None
        super().__init__(PlanningModuleSubmoduleTypes.INSTRUMENT_CAPABILITY.value, parent_module, submodules=[],
                         n_timed_coroutines=2)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            self.request_msg = msg.content
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        ## Internal coroutines
        check_database = asyncio.create_task(self.check_database())
        check_database.set_name (f'{self.name}_check_database')
        coroutines.append(check_database)

        broadcast_meas_req = asyncio.create_task(self.broadcast_meas_req())
        broadcast_meas_req.set_name (f'{self.name}_broadcast_meas_req')
        coroutines.append(broadcast_meas_req)

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
        return


    async def broadcast_meas_req(self):
        try:
            while True:
                if self.to_be_sent:
                    msg = InternalMessage(self.name, PlanningModuleSubmoduleTypes.OBSERVATION_PLANNING.value, self.msg_content)
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
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            self.print_observers(driver,sc_name)
            driver.close()
        except:
            self.log(f'Connection to Neo4j is not working! Make sure it\'s running and check the password!')
        

    def print_observers(self,driver,sc_name):
        with driver.session() as session:
            product = "None"
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
        super().__init__(PlanningModuleSubmoduleTypes.OBSERVATION_PLANNING.value, parent_module, submodules=[],
                         n_timed_coroutines=1)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module==PlanningModuleSubmoduleTypes.INSTRUMENT_CAPABILITY.value):
                self.task_list.append(msg.content)
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        ## Internal coroutines
        create_plan = asyncio.create_task(self.create_plan())
        create_plan.set_name (f'{self.name}_create_plan')
        coroutines.append(create_plan)

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
        return


    async def create_plan(self):
        try:
            while True:
                if(len(self.task_list) > 0):
                    # replace this with an actual planner!
                    for i in range(len(self.task_list)):
                        self.plan.append(self.task_list[i])
                    plan_msg = InternalMessage(self.name, PlanningModuleSubmoduleTypes.PREDICTIVE_MODELS.value, self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class PredictiveModelsModule(Module):
    def __init__(self, parent_module) -> None:
        self.agent_state = None
        self.plan = None
        super().__init__(PlanningModuleSubmoduleTypes.PREDICTIVE_MODELS.value, parent_module, submodules=[],
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
        coroutines = []

        ## Internal coroutines
        predict_state = asyncio.create_task(self.predict_state())
        predict_state.set_name (f'{self.name}_predict_state')
        coroutines.append(predict_state)

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
        return

    async def predict_state(self):
        try:
            while True:
                if(self.plan is not None):
                    plan_msg = InternalMessage(self.name, PlanningModuleSubmoduleTypes.MEASUREMENT_PERFORMANCE.value, self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class MeasurementPerformanceModule(Module):
    def __init__(self, parent_module) -> None:
        self.plan = None
        super().__init__(PlanningModuleSubmoduleTypes.MEASUREMENT_PERFORMANCE.value, parent_module, submodules=[],
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
        coroutines = []

        ## Internal coroutines
        evaluate_performance = asyncio.create_task(self.evaluate_performance())
        evaluate_performance.set_name (f'{self.name}_evaluate_performance')
        coroutines.append(evaluate_performance)

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
        return


    async def evaluate_performance(self):
        try:
            while True:
                if(self.plan is not None):
                    for i in range(len(self.plan)):
                        event = self.plan[i]
                        self.log(event)
                        observation_time = 20.0
                        delta = observation_time - float(event["time"])
                        lagfunc = -0.08182 * np.log(delta)+0.63182 # from molly's ppt on google drive
                        event["meas_perf_value"] = lagfunc
                        self.plan[i] = event
                    plan_msg = InternalMessage(self.name, PlanningModuleSubmoduleTypes.OBSERVATION_PLANNING.value, self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return