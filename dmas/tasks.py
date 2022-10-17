"""

MODULE TASKS

"""

"""
-------------------------------
COMPONENT TASKS
-------------------------------
"""
from utils import *


class ComponentTask:
    def __init__(self, component: str) -> None:
        """
        Abstract component task class meant to communicate a task to be performed by a specific component

        component:
            Name of component to perform the task
        """
        self.component : str = component

class ComponentAbortTask(ComponentTask):
    def __init__(self, component: str, target_task : ComponentTask) -> None:
        """
        Informs a component to abort a task that is currently being performed or is scheduled to be performed
        
        component:
            Name of component to perform the abort command
        target_task:
            Task to be aborted
        """
        super().__init__(component)
        self.target_task = target_task

class ComponentMaintenanceTask(ComponentTask):
    def __init__(self, component: str) -> None:
        """
        Abstract component task representing maintenance tasks to be performed to the component. 
        Includes tasks that regulate a component's status, health, or power-supply.
        """
        super().__init__(component)

class ComponentActuationTask(ComponentMaintenanceTask):
    def __init__(self, component: str, actuation_status: ComponentStatus) -> None:
        """
        Tasks a specific component to actuate on or off

        component:
            Name of component to be actuated
        actuation_status:
            Status of the component actuation to be set by this task
        """
        super().__init__(component)
        self.component_status : ComponentStatus = actuation_status

class DisableComponentTask(ComponentActuationTask):
    def __init__(self, component: str) -> None:
        """
        Turns OFF a component
        """
        super().__init__(component, ComponentStatus.OFF)

class EnableComponentTask(ComponentActuationTask):
    def __init__(self, component: str) -> None:
        """
        Turns ON a component
        """
        super().__init__(component, ComponentStatus.ON)

class ReceivePowerTask(ComponentMaintenanceTask):
    def __init__(self, component: str, power_to_supply : float) -> None:
        """
        Tells a specific component that it is receiving some amount of power from the EPS

        component:
            name of component to supply power
        power_to_supply:
            amout of power supplied in [W]
        """
        super().__init__(component)
        self.power_to_supply = power_to_supply

class StopReceivingPowerTask(ReceivePowerTask):
    def __init__(self, component: str, power_supplied: float) -> None:
        """
        Tells a specific component that it is no longer receiving some amount of power from the EPS

        component:
            name of component to supply power
        power_supplied:
            amout of power being taken away in [W]
        """
        super().__init__(component, -power_supplied)

class ProvidePowerTask(ComponentTask):
    def __init__(self, eps_component: str, power_to_supply : float, target : str) -> None:
        """
        Tasks a component from the EPS subsystem to provide power to another component

        eps_component:
            name of eps component to provide power
        power_to_supply:
            amout of power to be supplied in [W]
        target:
            name of component to be supplied with power
        """
        super().__init__(eps_component)
        self.power_to_supply = power_to_supply
        self.target = target

class StopProvidingPowerTask(ProvidePowerTask):
    def __init__(self, eps_component: str, power_to_stop: float, target: str) -> None:
        """
        Tasks a component from the EPS subsystem to stop providing power to another component

        eps_component:
            name of eps component to provide power
        power_to_stop:
            amout of power to no longer be supplied in [W]
        target:
            name of component to be deprived of power
        """
        super().__init__(eps_component, -power_to_stop, target)

class SaveToMemoryTask(ComponentTask):
    def __init__(self, target_lat: float, target_lon: float, data : str) -> None:
        """
        Instructs component to save observation data in internal memory 

        target_lat:
            lattitude of the target in [°]
        target_lon:
            longitude of the target in [°]
        data:        
            data to be saved
        """
        super().__init__(ComponentNames.ONBOARD_COMPUTER.value)
        self._target = (target_lat, target_lon)
        self._data = data

    def get_data(self):
        return self._data

    def get_target(self):
        return self._target

    def get_target_lat(self):
        lat, _ = self._target
        return lat

    def get_target_lon(self):
        _, lon = self._target
        return lon

class DeleteFromMemoryTask(SaveToMemoryTask):
    def __init__(self, target_lat: float, target_lon: float, data : str) -> None:
        """
        Instructs component to delete data from internal memory 
        """
        super().__init__(ComponentNames.ONBOARD_COMPUTER.value, target_lat, target_lon, data)
        
class MeasurementTask(ComponentTask):
    def __init__(self, instrument_name: str, duration : float, target_lat :float, target_lon : float, attitude_state : dict) -> None:
        """
        Instructs an instrument to perform a measurement.

        instrument_name:
            name of instrument to perform measurement
        duration:
            duration of measurement in [s]
        target_lat:
            latitude of target in [°]
        target_lon:
            longitude of target in [°]
        attitude_state:
            attitude of the agent
        """
        super().__init__(instrument_name)
        self.duration = duration
        self.target = [target_lat, target_lon]
        self.attitude_state = attitude_state

class ControlSignalTask(ComponentTask):
    def __init__(self, component, control_signal: float) -> None:
        """
        Gives a control signal to an atittude actuator to perform a maneuver.

        component:
            target component performing the maneuver
        control_signal:
            value of the step control signal being given to the actuator. Must be a value within [0, 1]
        """
        super().__init__(component)
        self.control_signal = control_signal

        if control_signal < 0 or 1 < control_signal:
            raise Exception("Control signal must be a value between [0, 1]!")

class AccelerationUpdateTask(ComponentTask):
    def __init__(self, actuator_name : str, angular_acceleration : list) -> None:
        """
        Informs IMU that a component is excerting some angular acceleration vector onto the spacecraft

        actuator_name:
            name of component exerting the angular acceleration vector in question
        angular_acceleration:
            angular acceleration being excerted on the spacecraft in [rad/s^2] in the body-fixed frame
        """
        super().__init__(ComponentNames.IMU.value)
        self.actuator_name = actuator_name
        self.angular_acceleration = angular_acceleration

class AttitudeUpdateTask(ComponentTask):
    def __init__(self, new_angular_pos, new_angular_vel) -> None:
        """
        Manually updates the attitude in an IMU
        """
        super().__init__(ComponentNames.IMU.value)
        self.new_angular_pos = new_angular_pos
        self.new_angular_vel = new_angular_vel        

class TransmitMessageTask(ComponentTask):
    def __init__(self, target_agent: str, msg, timeout : float) -> None:
        """
        Instructs the transmitter component to send a message to another agent
        
        target_agent:
            target agent to receive the message
        msg:
            message being transmitted
        timeout:
            transmission timeout in [s]
        """
        super().__init__(ComponentNames.TRANSMITTER.value)
        self.target_agent = target_agent
        self.msg = msg
        self.timeout = timeout
    
class ReceiveMessageTransmission(ComponentTask):
    def __init__(self) -> None:
        """
        Instructs comms receiver to be open for message transmission reception 
        """
        super().__init__(ComponentNames.RECEIVER.value)

"""
-------------------------------
SUBSYSTEM TASKS
-------------------------------
"""
class SubsystemTask:
    def __init__(self, subsystem: str) -> None:
        """
        Abstract subsystem task class meant to communicate a task to be performed by a particular subsystem

        subsystem:
            Name of subsystem to perform the task
        """
        self.subsystem : str = subsystem

class SubsystemAbortTask(SubsystemTask):
    def __init__(self, subsystem: str, target_task : SubsystemTask) -> None:
        """
        Informs a subsystem that it must abort a task that is currently being performed or is scheduled to be performed
        
        subsystem:
            Name of the subsystem to perform the abort command
        target_task:
            Task to be aborted
        """
        super().__init__(subsystem)
        self.target_task = target_task

class PowerSupplyRequestTask(SubsystemTask):
    def __init__(self, target : str, power_requested : float) -> None:
        """
        Tasks the EPS to provide power to a specific component

        target:
            name of the component to be powered
        power_requested:
            amount of power being requested in [W]
        """
        super().__init__(SubsystemNames.EPS.value)
        self.target = target
        self.power_requested = power_requested

class PowerSupplyStopRequestTask(PowerSupplyRequestTask):
    def __init__(self, target: str, power_supplied: float) -> None:
        """
        Tasks the EPS to stop providing power to a specific component

        target:
            name of the component to be powered
        power_supplied:
            amount of power being to no longer be provided to the component in [W]
        """
        super().__init__(target, -power_supplied)

class PerformAttitudeManeuverTask(SubsystemTask):
    def __init__(self, target_angular_pos : list, target_angular_vel = list) -> None:
        """
        Tasks the ADCS to perform an attitude maneouver

        target_angular_pos:
            quaternion vector describing the target attitude of the agent
        target_angular_pos:
            quaternion vector describing the target angular velocity of the agent
        """
        super().__init__(SubsystemNames.ADCS.value)
        self.target_angular_pos = target_angular_pos
        self.target_angular_vel = target_angular_vel

class PerformMeasurement(SubsystemTask):
    def __init__(self, target_lat : float, target_lon : float, instruments : list, durations : list) -> None:
        """
        Instructs the payload subsystem to perform a measurement of a target lat-lon with 
        a given list of instruments for a given set of durations
    
        target_lat:
            target latitude in [°]
        target_lon:
            target longitude in [°]
        instruments:
            list of instruments to perform the measurement at the same time
        duration:
            list of duration of each instrument measurement
        """
        super().__init__(SubsystemNames.PAYLOAD.value)
        self.target = (target_lat, target_lon)

        self.instruments = []
        for instrument in instruments:
            self.instruments.append(instrument)

        self.durations = []
        for duration in durations:
            self.durations.append(duration)

"""
-------------------------------
PLATOFRM TASK
-------------------------------
"""
class PlatformTask:
    def __init__(self) -> None:
        """
        Abstract platform task class meant to communicate a task to be performed by the agent's platform
        """
        return

class PlatformAbortTask(PlatformTask):
    def __init__(self, target_task : PlatformTask) -> None:
        """
        Informs a subsystem that it must abort a platform-level task that is currently being performed or is scheduled to be performed
        
        target_task:
            Task to be aborted
        """
        super().__init__()
        self.target_task = target_task

class ObservationTask(PlatformTask):
    def __init__(self, target_lan : float, target_lon : float, instrument_list : list, durations : list) -> None:
        super().__init__()
        self.target = (target_lan, target_lon)

        self.instrument_list = []
        for instrument in instrument_list:
            self.instrument_list.append(instrument)

        self.durations = []
        for duration in durations:
            self.durations.append(duration)

    def get_target(self):
        return self.target

"""
-------------------------------
PLANNER TASK
-------------------------------
"""
class PlannerTask:
    def __init__(self) -> None:
        """
        Abstract platform task class meant to communicate from obs planner to ops planner
        """
        return

class ObservationPlannerTask(PlannerTask):
    def __init__(self, target_lat : float, target_lon : float, science_val: float, instrument_list : list, start: float, end: float) -> None:
        super().__init__()
        self.target = (target_lat, target_lon)
        self.science_val = science_val

        self.instrument_list = []
        for instrument in instrument_list:
            self.instrument_list.append(instrument)

        self.start = start
        self.end = end

    def get_target(self):
        return self.target

class ChargePlannerTask(PlannerTask):
    def __init__(self, start: float, end: float) -> None:
        super().__init__()

        self.start = start
        self.end = end

"""

MODULE REQUESTS

"""

class Request:
    def __init__(self, req_type : type) -> None:
        self._type = req_type

class MeasurementRequest(Request):
    def __init__(self, measurement_type : type, target_lat : float, target_lon: float, science_val: float = 0) -> None:
        super().__init__(measurement_type)
        self._target = (target_lat, target_lon)
        self._science_val = science_val

    def get_measurement_type(self):
        return self._type

    def get_target(self):
        return self._target

    def set_science_val(self, science_val : float):
        self._science_val = science_val

    def get_science_val(self):
        return self._science_val

class InformationRequest(Request):
    def __init__(self, data_type : type, target_lat : float, target_lon: float) -> None:
        super().__init__(data_type)
        self._target = (target_lat, target_lon)

    def get_data_type(self):
        return self._type

    def get_target(self):
        return self._target

class DataProcessingRequest(Request):
    def __init__(self, data_type: type, target_lat: float, target_lon: float, data : str) -> None:
        super().__init__(data_type)
