import asyncio
import numpy as np
import logging
from modules import Module
from messages import *
from neo4j import GraphDatabase
from utils import PlanningSubmoduleTypes
from orbitdata import OrbitData
from tasks import MeasurementRequest

class PlanningModule(Module):
    def __init__(self, parent_agent : Module, scenario_dir : str) -> None:
        super().__init__(AgentModuleTypes.PLANNING_MODULE.value, parent_agent, [], 0)
        self.scenario_dir = scenario_dir
        self.submodules = [
            InstrumentCapabilityModule(self),
            ObservationPlanningModule(self),
            OperationsPlanningModule(self),
            PredictiveModelsModule(self),
            MeasurementPerformanceModule(self)
        ]

class InstrumentCapabilityModule(Module):
    def __init__(self, parent_module) -> None:
        self.event_msg_queue = []
        self.capable_msg_queue = []
        super().__init__(PlanningSubmoduleTypes.INSTRUMENT_CAPABILITY.value, parent_module, submodules=[],
                         n_timed_coroutines=2)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module == ScienceSubmoduleTypes.SCIENCE_VALUE.value):
                self.event_msg_queue.append(msg)
            else:
                self.log(f'Unsupported message type for this module.')
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
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


    async def broadcast_meas_req(self):
        try:
            while True:
                for capable_msg in self.capable_msg_queue:
                    msg = InternalMessage(self.name, PlanningSubmoduleTypes.OBSERVATION_PLANNER.value, capable_msg.content)
                    await self.parent_module.send_internal_message(msg)
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
                for event_msg in self.event_msg_queue:
                    self.queryGraphDatabase("bolt://localhost:7687", "neo4j", "ceosdb", "OLI", event_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

    def queryGraphDatabase(self, uri, user, password, sc_name,event_msg):
        try:
            self.log(f'Querying graph database')
            driver = GraphDatabase.driver(uri, auth=(user, password))
            self.print_observers(driver,sc_name,event_msg)
            driver.close()
        except Exception as e:
            print(e)
            self.log(f'Connection to Neo4j is not working! Make sure it\'s running and check the password!')
        

    def print_observers(self,driver,sc_name,event_msg):
        with driver.session() as session:
            product = "None"
            self.log(f'In print observers')
            if(event_msg.content.content["product_type"] == "chlorophyll-a"):
                self.log(f'In if in print observers')
                product = "Ocean chlorophyll concentration"
            observers = session.read_transaction(self.get_observers, title=product)
            for observer in observers:
                if(observer.get("name") == sc_name):
                    self.log(f'Matching instrument!')
                    event_msg.content.content["Measurable status"] = "Able to be measured"
                    self.capable_msg_queue.append(event_msg)
                    self.event_msg_queue.remove(event_msg)

    @staticmethod
    def get_observers(tx, title): # (1)
        result = tx.run("""
            MATCH (p:Sensor)-[r:OBSERVES]->(:ObservableProperty {name: $title})
            RETURN p
        """, title=title)

        # Access the `p` value from each record
        return [ record["p"] for record in result ]

class ObservationPlanningModule(Module):
    def __init__(self, parent_module : Module) -> None:
        self.obs_list = []
        self.obs_plan = []
        self.orbit_data: dict = OrbitData.from_directory(parent_module.scenario_dir)
        self.orbit_data = self.orbit_data[parent_module.parent_module.name]
        super().__init__(PlanningSubmoduleTypes.OBSERVATION_PLANNER.value, parent_module)

        # this is just for testing!
        initial_obs = ObservationPlannerTask(0.0,-32.0,1.0,["OLI"],0.0,1.0)
        self.obs_list.append(initial_obs)

    # async def activate(self):
    #     await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module==PlanningSubmoduleTypes.INSTRUMENT_CAPABILITY.value):
                self.obs_list.append(msg.content)
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
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
                subroutine : asyncio.Task
                subroutine.cancel()
                await subroutine
        
        except asyncio.CancelledError:
            for coroutine in coroutines:
                coroutine : asyncio.Task
                if not coroutine.done():
                    coroutine.cancel()
                    await coroutine


    async def create_plan(self):
        try:
            while True:
                sim_wait = None
                if(len(self.obs_list) > 0):
                    # replace this with an actual planner!
                    for i in range(len(self.obs_list)):
                        obs = self.obs_list[i]
                        #gp_accesses = self.orbit_data.get_ground_point_accesses_future(task["lat"], task["lon"], self.get_current_time())
                        gp_accesses = self.orbit_data.get_ground_point_accesses_future(0.0, -32.0, self.get_current_time())
                        gp_access_list = []
                        for _, row in gp_accesses.iterrows():
                            gp_access_list.append(row)
                        print(gp_accesses)
                        if(len(gp_accesses) != 0):
                            obs.start = gp_access_list[0]['time index']
                            obs.end = obs.start + 5
                            self.obs_plan.append(obs)
                    self.obs_list = []
                    plan_msg = InternalMessage(self.name, PlanningSubmoduleTypes.OPERATIONS_PLANNER.value, self.obs_plan)
                    await self.parent_module.send_internal_message(plan_msg)
                
                sim_wait = asyncio.create_task(self.sim_wait(1.0))
                await sim_wait
                
        except asyncio.CancelledError:
            if sim_wait is not None and not sim_wait.done():
                sim_wait : asyncio.Task
                sim_wait.cancel()
                await sim_wait

class OperationsPlanningModule(Module):
    def __init__(self, parent_module) -> None:
        self.obs_plan = []
        self.ops_plan = []
        self.modeled_states = []
        super().__init__(PlanningSubmoduleTypes.OPERATIONS_PLANNER.value, parent_module, submodules=[],
                         n_timed_coroutines=2)

    # async def activate(self):
    #     await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module==PlanningSubmoduleTypes.OBSERVATION_PLANNER.value):
                self.obs_plan = msg.content
            elif(msg.src_module==PlanningSubmoduleTypes.PREDICTIVE_MODEL.value):
                self.modeled_states.append(msg.content)
            else:
                self.log(f'Unsupported message type for this module.)')
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
            ## Internal coroutines
            create_ops_plan = asyncio.create_task(self.create_ops_plan())
            create_ops_plan.set_name (f'{self.name}_create_ops_plan')
            coroutines.append(create_ops_plan)

            execute_ops_plan = asyncio.create_task(self.execute_ops_plan())
            execute_ops_plan.set_name (f'{self.name}_execute_ops_plan')
            coroutines.append(execute_ops_plan)

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


    async def create_ops_plan(self):
        try:
            while True:
                # Replace with basic module that adds charging to plan
                if(len(self.obs_plan) > 0 and len(self.ops_plan) == 0):
                    plan_beginning = self.get_current_time()
                    starts = []
                    ends = []
                    for obs in self.obs_plan:
                        starts.append(obs.start)
                        ends.append(obs.end)
                    charge_task = ChargePlannerTask(plan_beginning,starts[0])
                    self.ops_plan.append(charge_task)
                    for i in range(len(starts)):
                        if(i+1 < len(starts)):
                            charge_task = ChargePlannerTask(ends[i],starts[i+1])
                            self.ops_plan.append(charge_task)
                        obs_task = self.obs_plan[i]
                        self.ops_plan.append(obs_task)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return
    
    async def execute_ops_plan(self):
        try:
            while True:
                # Replace with basic module that adds charging to plan
                curr_time = self.get_current_time()
                for task in self.ops_plan:
                    print(task)
                    if(isinstance(task,ChargePlannerTask)):
                        self.log(f'Telling platform sim to charge!')
                        # currently doing nothing when 'charging'
                    elif(isinstance(task,ObservationPlannerTask)):
                        print(task.target)
                        print(task.start)
                        print(task.end)
                        if(5 < curr_time < 10): # TODO should be between task start and task end but this is for testing
                            obs_task = ObservationTask(task.target[0], task.target[1], [InstrumentNames.TEST.value], [1])
                            msg = PlatformTaskMessage(self.name, AgentModuleTypes.ENGINEERING_MODULE.value, obs_task)
                            await self.send_internal_message(msg)
                    else:
                        self.log(f'Currently unsupported task type!')

                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class PredictiveModelsModule(Module):
    def __init__(self, parent_module) -> None:
        self.agent_state = None
        self.obs_plan = None
        self.ops_plan = None
        super().__init__(PlanningSubmoduleTypes.PREDICTIVE_MODEL.value, parent_module, submodules=[],
                         n_timed_coroutines=1)

    # async def activate(self):
    #     await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module == PlanningSubmoduleTypes.OBSERVATION_PLANNER.value):
                self.obs_plan = msg.content
            elif(msg.src_module == PlanningSubmoduleTypes.OPERATIONS_PLANNER.value):
                self.ops_plan = msg.content
            else:
                self.log(f'Message from unsupported module.')
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
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

    async def predict_state(self):
        try:
            while True:
                if(self.obs_plan is not None):
                    plan_msg = InternalMessage(self.name, PlanningSubmoduleTypes.MEASUREMENT_PERFORMANCE.value, self.obs_plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)
        except asyncio.CancelledError:
            return

class MeasurementPerformanceModule(Module):
    def __init__(self, parent_module) -> None:
        self.plan = None
        super().__init__(PlanningSubmoduleTypes.MEASUREMENT_PERFORMANCE.value, parent_module, submodules=[],
                         n_timed_coroutines=1)

    # async def activate(self):
    #     await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module == PlanningSubmoduleTypes.PREDICTIVE_MODEL.value):
                self.plan = msg.content
            else:
                self.log(f'Unsupported message type for this module.')
        except asyncio.CancelledError:
            return

    async def coroutines(self):
        coroutines = []

        try:
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


    async def evaluate_performance(self):
        try:
            while True:
                if(self.plan is not None):
                    for i in range(len(self.plan)):
                        event = self.plan[i]
                        observation_time = 20.0
                        delta = observation_time - float(event.content["time"])
                        lagfunc = -0.08182 * np.log(delta)+0.63182 # from molly's ppt on google drive
                        event.content["meas_perf_value"] = lagfunc
                        self.plan[i] = event
                    plan_msg = InternalMessage(self.name, PlanningSubmoduleTypes.OBSERVATION_PLANNER.value, self.plan)
                    await self.parent_module.send_internal_message(plan_msg)
                await self.sim_wait(1.0)

        except asyncio.CancelledError:
            return