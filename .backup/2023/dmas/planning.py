import asyncio
import numpy as np
import logging
import csv
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

        parent_agent = self.get_top_module()
        mission_profiles = dict()
        preplans = dict()
        spacecraft_list = parent_agent.mission_dict.get('spacecraft')
        for spacecraft in spacecraft_list:
            name = spacecraft.get('name')
            # land coverage data metrics data
            mission_profile = spacecraft.get('missionProfile')
            preplan = spacecraft.get('preplan')
            mission_profiles[name] = mission_profile
            preplans[name] = preplan
            
        self.mission_profile = mission_profiles[parent_agent.name]
        self.preplan = preplans[parent_agent.name]

        
        self.submodules = [
            InstrumentCapabilityModule(self),
            ObservationPlanningModule(self),
            OperationsPlanningModule(self),
            #PredictiveModelsModule(self),
            #MeasurementPerformanceModule(self)
        ]

    def check_maneuver_feasibility(self,curr_angle,new_angle,curr_time,new_time):
        """
        Checks to see if the specified angle change violates the maximum slew rate constraint.
        """
        moved = False
        if(abs(curr_angle-new_angle) < 7.5):
            return True, False
        if(new_time==curr_time):
            return False, False
        slew_rate = abs(new_angle-curr_angle)/abs(new_time-curr_time)
        max_slew_rate = 1.0 # deg / s
        #slewTorque = 4 * abs(np.deg2rad(new_angle)-np.deg2rad(curr_angle))*0.05 / pow(abs(new_time-curr_time),2)
        #maxTorque = 4e-3
        moved = True
        return slew_rate < max_slew_rate, moved

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
                if isinstance(msg.content, MeasurementRequest):
                    # if a measurement request is received, forward to instrument capability submodule
                    self.log(f'Received measurement request from \'{msg.src_module}\'!', level=logging.INFO)
                    msg.dst_module = PlanningSubmoduleTypes.INSTRUMENT_CAPABILITY.value

                    await self.send_internal_message(msg)

                else:
                    self.log(f'Internal messages with contents of type: {type(msg.content)} not yet supported. Discarding message.')

        except asyncio.CancelledError:
            return

class InstrumentCapabilityModule(Module):
    def __init__(self, parent_module) -> None:
        super().__init__(PlanningSubmoduleTypes.INSTRUMENT_CAPABILITY.value, parent_module, submodules=[],
                         n_timed_coroutines=0)

    async def activate(self):
        await super().activate()

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(isinstance(msg.content, MeasurementRequest)):
                parent_agent = self.get_top_module()
                instrument = parent_agent.payload[parent_agent.name]["name"]
                if self.queryGraphDatabase("bolt://localhost:7687", "neo4j", "ceosdb", instrument, msg):
                    msg.dst_module = PlanningSubmoduleTypes.OBSERVATION_PLANNER.value
                    await self.send_internal_message(msg)
            else:
                self.log(f'Unsupported message type for this module.')
        except asyncio.CancelledError:
            return

    def queryGraphDatabase(self, uri, user, password, instrument,event_msg):
        """
        Sends message to neo4j database with query included.
        """
        try:
            capable = False
            self.log(f'Querying knowledge graph...', level=logging.DEBUG)
            driver = GraphDatabase.driver(uri, auth=(user, password))
            capable = self.can_observe(driver,instrument,event_msg)
            driver.close()
            return capable
        except Exception as e:
            print(e)
            self.log(f'Connection to Neo4j is not working! Make sure it\'s running and check the password!', level=logging.ERROR)
            return False
        

    def can_observe(self,driver,instrument,event_msg):
        """
        Checks if the onboard instrument can observe the desired product.
        """
        capable = False
        with driver.session() as session:
            products = ["None"]
            if "tss" in event_msg.content._type:
                products.append("Ocean chlorophyll concentration")
            if "altimetry" in event_msg.content._type:
                products.append("Sea level")
            if len(products) == 0:
                self.log(f'Unsupported observable type.',level=logging.INFO)
            for product in products:
                #self.log(f'Product: {product}',level=logging.INFO)
                observers = session.read_transaction(self.get_observers, title=product)
                for observer in observers:
                    #self.log(f'Observer: {observer.get("name")}',level=logging.INFO)
                    #self.log(f'Instrument: {instrument}',level=logging.INFO)
                    if(observer.get("name") == instrument):
                        self.log(f'Matching instrument in knowledge graph!', level=logging.DEBUG)
                        capable = True
            if capable is False:
                self.log(f'The instruments onboard cannot observe the requested observables.',level=logging.DEBUG)
        return capable


    @staticmethod
    def get_observers(tx, title): # (1)
        """
        Generates expression to query the KG.
        """
        result = tx.run("""
            MATCH (p:Sensor)-[r:OBSERVES]->(:ObservableProperty {name: $title})
            RETURN p
        """, title=title)

        # Access the `p` value from each record
        return [ record["p"] for record in result ]

class ObservationPlanningModule(Module):
    def __init__(self, parent_module : Module) -> None:
        self.obs_plan = []
        self.obs_candidates = []
        self.orbit_data: dict = OrbitData.from_directory(parent_module.scenario_dir)
        self.orbit_data = self.orbit_data[parent_module.parent_module.name]
        super().__init__(PlanningSubmoduleTypes.OBSERVATION_PLANNER.value, parent_module)

    async def activate(self):
        await super().activate()
        
        # Initialize observation list and plan
        self.obs_list = asyncio.Queue()

        await self.initialize_plan()

    async def initialize_plan(self):
        """
        Creates an initial plan for missions with preplanning included.
        """
        if (self.parent_module.mission_profile=="3D-CHESS" and self.parent_module.preplan=="True") or self.parent_module.mission_profile=="agile":
            parent_agent = self.get_top_module()
            instrument = parent_agent.payload[parent_agent.name]["name"]
            # points = np.zeros(shape=(2000, 5))
            # with open(self.parent_module.scenario_dir+'resources/chlorophyll_baseline.csv') as csvfile:
            #     reader = csv.reader(csvfile)
            #     count = 0
            #     for row in reader:
            #         if count == 0:
            #             count = 1
            #             continue
            #         points[count-1,:] = [row[0], row[1], row[2], row[3], row[4]]
            #         count = count + 1
            points = np.zeros(shape=(1000, 4))
            with open(self.parent_module.scenario_dir+'resources/riverATLAS.csv') as csvfile:
                reader = csv.reader(csvfile)
                count = 0
                for row in reader:
                    if count == 0:
                        count = 1
                        continue
                    points[count-1,:] = [row[0], row[1], row[2], row[3]]
                    count = count + 1
            obs_list = []
            for i in range(len(points[:, 0])):
                lat = points[i, 0]
                lon = points[i, 1]
                obs = ObservationPlannerTask(lat,lon,1.0,[instrument],0.0,1.0)
                obs_list.append(obs)
            for obs in obs_list:
                    # estimate next observation opportunities
                    gp_accesses = self.orbit_data.get_ground_point_accesses_future(obs.target[0], obs.target[1], self.get_current_time())
                    #self.log(f'Current time: {self.get_current_time()}',level=logging.INFO)
                    gp_access_list = []
                    for _, row in gp_accesses.iterrows():
                        gp_access_list.append(row)
                    #self.log(f'Length of gp access list: {len(gp_access_list)}',level=logging.INFO)
                    if(len(gp_accesses) != 0):
                        self.log(f'Adding observation candidate!',level=logging.DEBUG)
                        obs.start = gp_access_list[0]['time index']
                        obs.end = obs.start
                        obs.angle = gp_access_list[0]['look angle [deg]']
                        unique_location = True
                        for obs_can in self.obs_candidates:
                            if obs_can.target == obs.target:
                                unique_location = False
                        if unique_location:
                            self.obs_candidates.append(obs)
            old_obs_plan = self.obs_plan.copy()
            if self.parent_module.mission_profile=="nadir":
                self.obs_plan = self.nadir_planner(self.obs_candidates.copy())
            else:
                self.obs_plan = self.rule_based_planner(self.obs_candidates.copy())
                self.log(f'Length of new observation plan: {len(self.obs_plan)}',level=logging.INFO)
            # schedule observation plan and send to operations planner for further development
            if(self.obs_plan != old_obs_plan):
                plan_msg = InternalMessage(self.name, PlanningSubmoduleTypes.OPERATIONS_PLANNER.value, self.obs_plan)
                await self.parent_module.send_internal_message(plan_msg)
        elif self.parent_module.mission_profile=="nadir":
            parent_agent = self.get_top_module()
            instrument = parent_agent.payload[parent_agent.name]["name"]
            # points = np.zeros(shape=(2000, 5))
            # with open(self.parent_module.scenario_dir+'resources/chlorophyll_baseline.csv') as csvfile:
            #     reader = csv.reader(csvfile)
            #     count = 0
            #     for row in reader:
            #         if count == 0:
            #             count = 1
            #             continue
            #         points[count-1,:] = [row[0], row[1], row[2], row[3], row[4]]
            #         count = count + 1
            points = np.zeros(shape=(1000, 4))
            with open(self.parent_module.scenario_dir+'resources/riverATLAS.csv') as csvfile:
                reader = csv.reader(csvfile)
                count = 0
                for row in reader:
                    if count == 0:
                        count = 1
                        continue
                    points[count-1,:] = [row[0], row[1], row[2], row[3]]
                    count = count + 1
            obs_list = []
            for i in range(len(points[:, 0])):
                lat = points[i, 0]
                lon = points[i, 1]
                obs = ObservationPlannerTask(lat,lon,1.0,[instrument],0.0,1.0)
                gp_accesses = self.orbit_data.get_ground_point_accesses_future(obs.target[0], obs.target[1], self.get_current_time())
                gp_access_list = []
                for _, row in gp_accesses.iterrows():
                    gp_access_list.append(row)
                #print(gp_accesses)
                if(len(gp_accesses) != 0):
                    self.log(f'Adding observation candidate!',level=logging.DEBUG)
                    obs.start = gp_access_list[0]['time index']
                    obs.end = obs.start # TODO change this hardcode
                    obs.angle = gp_access_list[0]['look angle [deg]']
                    obs_list.append(obs)
        else:
            obs_list = []
        await self.obs_list.put(obs_list)

    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if isinstance(msg.content, MeasurementRequest):
                if self.parent_module.mission_profile=="3D-CHESS":
                    meas_req = msg.content
                    parent_agent = self.get_top_module()
                    new_obs = ObservationPlannerTask(meas_req._target[0],meas_req._target[1],meas_req._science_val,parent_agent.payload[parent_agent.name],0.0,1.0,meas_req.metadata)
                    self.log(f'Measurement request: {meas_req._target[0]}, {meas_req._target[1]}',level=logging.INFO)
                    new_obs_list = []
                    new_obs_list.append(new_obs)
                    await self.obs_list.put(new_obs_list)
                elif self.parent_module.mission_profile=="agile":
                    self.log(f'Mission cannot replan based on new events.',level=logging.DEBUG)
                else:
                    self.log(f'Unsupported mission profile!',level=logging.DEBUG)
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
        """
        Creates observation plan. Provides list of all future observation candidates to the planners.
        """
        try:
            while True:
                # wait for observation request
                obs_list = await self.obs_list.get()
                self.log(f'Length of obs list: {len(obs_list)}',level=logging.INFO)
                for obs in obs_list:
                    # estimate next observation opportunities
                    gp_accesses = self.orbit_data.get_ground_point_accesses_future(obs.target[0], obs.target[1], self.get_current_time())
                    self.log(f'Current time: {self.get_current_time()}',level=logging.INFO)
                    gp_access_list = []
                    for _, row in gp_accesses.iterrows():
                        gp_access_list.append(row)
                    self.log(f'Length of gp access list: {len(gp_access_list)}',level=logging.INFO)
                    if(len(gp_accesses) != 0):
                        obs.start = gp_access_list[0]['time index']
                        obs.end = obs.start
                        obs.angle = gp_access_list[0]['look angle [deg]']
                        # unique_location = True
                        # for obs_can in self.obs_candidates:
                        #     if obs_can.target == obs.target:
                        #         unique_location = False
                        # if unique_location:
                        self.obs_candidates.append(obs)
                old_obs_plan = self.obs_plan.copy()
                curr_time = self.get_current_time()
                for obs_can in self.obs_candidates:
                    if(obs_can.start <= curr_time):
                        self.obs_candidates.remove(obs_can)
                if self.parent_module.mission_profile=="nadir":
                    self.obs_plan = self.nadir_planner(self.obs_candidates.copy())
                else:
                    self.obs_plan = self.rule_based_planner(self.obs_candidates.copy())
                    self.log(f'Length of new observation plan: {len(self.obs_plan)}',level=logging.INFO)
                # schedule observation plan and send to operations planner for further development
                if(self.obs_plan != old_obs_plan):
                    plan_msg = InternalMessage(self.name, PlanningSubmoduleTypes.OPERATIONS_PLANNER.value, self.obs_plan)
                    await self.parent_module.send_internal_message(plan_msg)

        except asyncio.CancelledError:
            return

    def rule_based_planner(self,obs_list):
        """
        Based on the "greedy planner" from Lemaitre et al. Incorporates reward information and future options to decide observation plan.
        """
        estimated_reward = 100.0
        rule_based_plan = []
        i = 0
        while i < 2:
            self.log(f'Estimated reward: {estimated_reward}',level=logging.DEBUG)
            rule_based_plan = []
            more_actions = True
            curr_time = 0.0
            curr_angle = 0.0
            total_reward = 0.0
            obs_list_copy = obs_list.copy()
            while more_actions:
                best_obs = None
                maximum = 0.0
                actions = self.get_action_space(curr_time,curr_angle,obs_list)
                if(len(actions) == 0):
                    break
                for action in actions:
                    duration = 86400.0*16.0
                    rho = (duration - action.end)/duration
                    e = rho * estimated_reward
                    adjusted_reward = action.science_val*self.meas_perf() + e
                    # if action.science_val > 5.0:
                    #     self.log(f'Science value greater than 5: {action.science_val} at {action.target} with angle {action.angle} and time {action.start} when curr_angle={curr_angle} and curr_time={curr_time}, adjusted_reward = {adjusted_reward} and maximum = {maximum}',level=logging.DEBUG)
                    if(adjusted_reward > maximum):
                        maximum = adjusted_reward
                        best_obs = action
                curr_time = best_obs.end
                curr_angle = best_obs.angle
                total_reward += best_obs.science_val*self.meas_perf()
                rule_based_plan.append(best_obs)
                obs_list.remove(best_obs)
                if(len(self.get_action_space(curr_time,curr_angle,obs_list)) == 0):
                    more_actions = False
            i += 1
            estimated_reward = total_reward
            obs_list = obs_list_copy
        return rule_based_plan

    def nadir_planner(self,obs_list):
        """
        Adds all observable points to observation plan.
        """
        nadir_plan = []
        more_actions = True
        curr_time = 0.0
        while more_actions:
            soonest = 100000
            soonest_action = None
            actions = self.get_action_space_nadir(curr_time,obs_list)
            if(len(actions) == 0):
                break
            for action in actions:
                if action.start < soonest:
                    soonest_action = action
                    soonest = action.start
            nadir_plan.append(soonest_action)
            obs_list.remove(soonest_action)
            curr_time = soonest_action.start
            if(len(self.get_action_space_nadir(curr_time,obs_list)) == 0):
                more_actions = False
        return nadir_plan

    def get_action_space_nadir(self,curr_time,obs_list):
        feasible_actions = []
        for obs in obs_list:
            if obs.start >= curr_time:
                feasible_actions.append(obs)
        return feasible_actions

    def get_action_space(self,curr_time,curr_angle,obs_list):
        feasible_actions = []
        for obs in obs_list:
            feasible, moved = self.parent_module.check_maneuver_feasibility(curr_angle,obs.angle,curr_time,obs.start)
            if obs.start >= curr_time and feasible:
                feasible_actions.append(obs)
        return feasible_actions

    def meas_perf(self):
        """
        Evaluates measurement performance based on Molly's work TODO add citation/ref
        """
        a = 8.9e-5
        b = 1.4e-3
        c = 6.1e-3
        d = 0.85
        parent_agent = self.get_top_module()
        instrument = parent_agent.payload[parent_agent.name]["name"]
        if(instrument=="VIIRS" or instrument=="OLI"):
            x = parent_agent.payload[parent_agent.name]["snr"]
            y = parent_agent.payload[parent_agent.name]["spatial_res"]
            z = parent_agent.payload[parent_agent.name]["spectral_res"]
            perf = a*pow(x,3)-b*pow(y,2)-c*np.log10(z)+d
        else:
            perf = 1
        #self.log(f'Measurement performance: {perf}',level=logging.INFO)
        return perf
            

class OperationsPlanningModule(Module):
    def __init__(self, parent_module) -> None:
        super().__init__(PlanningSubmoduleTypes.OPERATIONS_PLANNER.value, parent_module, submodules=[],
                         n_timed_coroutines=1)
        self.ops_plan = []

    async def activate(self):
        await super().activate()
        self.obs_plan = asyncio.Queue()


    async def internal_message_handler(self, msg):
        """
        Handles message intended for this module and performs actions accordingly.
        """
        try:
            if(msg.src_module==PlanningSubmoduleTypes.OBSERVATION_PLANNER.value):
                self.log(f'Received observation plan!',level=logging.DEBUG)
                await self.obs_plan.put(msg.content)
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
        """
        Converts the observation plan into an operations plan by adding charging and maneuvering. Also checks for observation feasibility in both maneuver agility and time.
        """
        try:
            while True:
                # Replace with basic module that adds charging to plan
                if self.parent_module.mission_profile=="3D-CHESS" or self.parent_module.mission_profile=="agile":
                    plan = await self.obs_plan.get()
                    self.log(f'Creating operations plan!',level=logging.INFO)
                    plan_beginning = self.get_current_time()
                    starts = []
                    ends = []
                    for obs in plan:
                        starts.append(obs.start)
                        ends.append(obs.end)
                    self.log(f'List of starts: {starts}',level=logging.DEBUG)
                    if len(starts) != 0:
                        charge_task = ChargePlannerTask(plan_beginning,starts[0])
                        #self.ops_plan.append(charge_task)
                        curr_angle = 0
                        curr_time = plan_beginning
                        for i in range(len(starts)):
                            if(i+1 < len(starts)):
                                charge_task = ChargePlannerTask(ends[i],starts[i+1])
                                #self.ops_plan.append(charge_task) TODO add back charge tasks
                            obs_task = plan[i]
                            feasible, moved = self.parent_module.check_maneuver_feasibility(curr_angle,obs_task.angle,curr_time,obs_task.start)
                            if curr_time <= obs_task.start and feasible:
                                self.log(f'Adding observation task at time {obs_task.start} to operations plan!',level=logging.DEBUG)
                                unique = True
                                for ops in self.ops_plan:
                                    if(ops.start == obs_task.start and ops.target == obs_task.target):
                                        unique = False
                                if unique:
                                    self.ops_plan.append(obs_task)
                                #self.log(f'Adding maneuver task from {curr_angle} to {obs_task.angle} to operations plan!',level=logging.DEBUG)
                                #maneuver_task = ManeuverPlannerTask(curr_angle,obs_task.angle,curr_time,obs_task.start+1)
                                #self.ops_plan.append(maneuver_task)
                                curr_time = obs_task.end
                                if moved:
                                    curr_angle = obs_task.angle
                            else:
                                self.log(f'Maneuver not feasible!',level=logging.DEBUG)
                    self.print_ops_plan()
                elif self.parent_module.mission_profile=="nadir":
                    plan = await self.obs_plan.get()
                    self.log(f'Creating operations plan!',level=logging.DEBUG)
                    plan_beginning = self.get_current_time()
                    starts = []
                    ends = []
                    for obs in plan:
                        starts.append(obs.start)
                        ends.append(obs.end)
                    self.log(f'List of starts: {starts}',level=logging.INFO)
                    if len(starts) != 0:
                        charge_task = ChargePlannerTask(plan_beginning,starts[0])
                        self.ops_plan.append(charge_task)
                        curr_time = plan_beginning
                        for i in range(len(starts)):
                            if(i+1 < len(starts)):
                                charge_task = ChargePlannerTask(ends[i],starts[i+1])
                                self.ops_plan.append(charge_task)
                            obs_task = plan[i]
                            if curr_time <= obs_task.start:
                                self.log(f'Adding observation task at time {obs_task.start} to operations plan!',level=logging.DEBUG)
                                self.ops_plan.append(obs_task)
                                curr_time = obs_task.end
        except asyncio.CancelledError:
            return
    
    async def execute_ops_plan(self):
        """
        Takes the ops plan and sends messages to other modules based on the ops plan. For example, sends observation tasks to the engineering module.
        """
        try:
            while True:
                # Replace with basic module that adds charging to plan
                curr_time = self.get_current_time()
                for task in self.ops_plan:
                    if(isinstance(task,ObservationPlannerTask)):
                        if(task.start <= curr_time):
                            #await self.sim_wait(1.0)
                            self.log(f'Sending observation task to engineering module!',level=logging.DEBUG)
                            self.log(f'Task metadata: {task.obs_info}',level=logging.DEBUG)
                            obs_task = ObservationTask(task.target[0], task.target[1], [InstrumentNames.TEST.value], [0.0], task.obs_info)
                            msg = PlatformTaskMessage(self.name, AgentModuleTypes.ENGINEERING_MODULE.value, obs_task)
                            self.ops_plan.remove(task)
                            await self.send_internal_message(msg)
                    elif(isinstance(task,ManeuverPlannerTask)):
                        if(task.start <= curr_time):
                            self.log(f'Sending maneuver task to engineering module!',level=logging.DEBUG)
                            perf_maneuver_task = PerformAttitudeManeuverTask((task.end-task.start),task.end_angle,0.0)
                            maneuver_task = ManeuverTask(perf_maneuver_task)
                            msg = PlatformTaskMessage(self.name, AgentModuleTypes.ENGINEERING_MODULE.value, maneuver_task)
                            self.ops_plan.remove(task)
                            await self.send_internal_message(msg)
                    else:
                        self.log(f'Currently unsupported task type!')
                await self.sim_wait(10.0)
        except asyncio.CancelledError:
            return
    
    def print_ops_plan(self):
        """
        Prints the operations plan.
        """
        for op in self.ops_plan:
            if(isinstance(op,ObservationPlannerTask)):
                self.log(f'Observation planned at {op.start} to observe {op.target}',level=logging.DEBUG)


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