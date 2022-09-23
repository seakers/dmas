import asyncio
import json
import os
import csv
from modules import Module
from messages import *
from neo4j import GraphDatabase

class PlanningModule(Module):
    def __init__(self, name, parent_module, scenario_dir, submodules=[], n_timed_coroutines=3) -> None:
        self.scenario_dir = scenario_dir
        super().__init__(name, parent_module, submodules, n_timed_coroutines)
        self.submodules = [
            InstrumentCapabilityModule(self)
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
            #self.to_be_sent = True
            self.request_msg = msg
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        self.log("Running instrument capability module coroutines")
        check_database = asyncio.create_task(self.check_database())
        #broadcast_meas_req = asyncio.create_task(self.broadcast_meas_req())
        await check_database
        self.log("1")
        check_database.cancel()
        self.log("2")
        #await broadcast_meas_req
        self.log("3")
        #broadcast_meas_req.cancel()
        self.log("Finished instrument capability module coroutines")


    async def broadcast_meas_req(self):
        try:
            while True:
                self.log(f'In broadcast meas req')
                if self.to_be_sent:
                    self.log(f'In self to be sent')
                    msg = InternalMessage(self.name, "MCCBA Module", self.msg_content)
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
                self.queryGraphDatabase("bolt://localhost:7687", "neo4j", "ceosdb", "OLI")
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

    def queryGraphDatabase(self, uri, user, password, sc_name):
        driver = GraphDatabase.driver(uri, auth=(user, password))
        self.print_observers(driver,sc_name)
        driver.close()

    def print_observers(self,driver,sc_name):
        with driver.session() as session:
            observers = session.read_transaction(self.get_observers, title="Ocean chlorophyll concentration")
            for observer in observers:
                if(observer.get("name") == sc_name):
                    self.log(f'Matching instrument!')
                    self.to_be_sent = True
                    self.msg_content = "Able to be measured"

    @staticmethod
    def get_observers(tx, title): # (1)
        result = tx.run("""
            MATCH (p:Sensor)-[r:OBSERVES]->(:ObservableProperty {name: $title})
            RETURN p
        """, title=title)

        # Access the `p` value from each record
        return [ record["p"] for record in result ]