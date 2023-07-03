
from abc import abstractmethod
import numpy as np
from typing import Union
from nodes.science.reqs import MeasurementRequest
from nodes.actions import *
from nodes.engineering.engineering import EngineeringModule
from dmas.agents import AbstractAgentState, AgentAction
from orbitpy.util import OrbitState
import propcov

class SimulationAgentTypes(Enum):
    SATELLITE = 'SATELLITE'
    UAV = 'UAV'
    GROUND_STATION = 'GROUND_STATION'

class SimulationAgentState(AbstractAgentState):
    """
    Describes the state of a 3D-CHESS agent
    """
    
    IDLING = 'IDLING'
    MESSAGING = 'MESSAGING'
    TRAVELING = 'TRAVELING'
    MANEUVERING = 'MANEUVERING'
    MEASURING = 'MEASURING'
    SENSING = 'SENSING'
    THINKING = 'THINKING'
    LISTENING = 'LISTENING'

    def __init__(   self, 
                    state_type : str,
                    pos : list,
                    vel : list,
                    engineering_module : EngineeringModule = None,
                    status : str = IDLING,
                    t : Union[float, int]=0,
                    **_
                ) -> None:
        """
        Creates an instance of an Abstract Agent State
        """
        super().__init__()
        
        self.state_type = state_type
        self.pos : list = pos
        self.vel : list = vel
        self.engineering_module : EngineeringModule = engineering_module
        self.status : str = status
        self.t : float = t

    def update_state(self, 
                        t : Union[int, float], 
                        status : str = None, 
                        state : dict = None) -> None:
        # update internal components
        if self.engineering_module is not None:
            self.engineering_module.update_state(t)

        # update position and velocity
        if state:
            self.pos, self.vel = state['pos'], state['vel']
        else:
            pos, vel = self.propagate(t)
            self.pos, self.vel = pos, vel

        self.t = t 
        self.status = status if status is not None else self.status

    def can_do(self, req : MeasurementRequest) -> bool:
        """
        Check if the parent agent is capable of performing a measurement request given its current state

        ### Arguments:
            - req (:obj:`MeasurementRequest`) : measurement request being considered

        ### Returns:
            - can_do (`bool`) : `True` if agent has the capability to perform a task of `False` if otherwise
        """
        # TODO include support for knowledge graph 

        

    @abstractmethod
    def propagate(self, tf : Union[int, float], **kwargs) -> tuple:
        """
        Propagator for the agent's dynamics through time.

        ### Arguments 
            - tf (`int` or `float`) : propagation end time in [s]

        ### Returns:
            - pos, vel (`tuple`) : tuple of updated position and velocity vectors
        """
        pass

    def perform_action(self, action : AgentAction, t : Union[int, float]) -> tuple:
        """
        Performs an action that may affect the agent's state.

        ### Arguments:
            - action (:obj:`AgentAction`): action to be performed
            - t (`int` or `double`): current simulation time in [s]
        
        ### Returns:
            - status (`str`): action completion status
            - dt (`float`): time to be waited by the agent
        """
        if isinstance(action, IdleAction):
            self.update_state(t, status=self.IDLING)
            if action.t_end > t:
                dt = action.t_end - t
                status = action.PENDING
            else:
                dt = 0.0
                status = action.COMPLETED
            return status, dt

        elif isinstance(action, TravelAction):
            return self.perform_travel(action, t)

        elif isinstance(action, ManeuverAction):
            return self.perform_maneuver(action, t)
        
        return action.ABORTED, 0.0

    def comp_vectors(self, v1 : list, v2 : list):
        """
        compares two vectors
        """
        dx = v1[0] - v2[0]
        dy = v1[1] - v2[1]
        dz = v1[2] - v2[2]

        dv = np.sqrt(dx**2 + dy**2 + dz**2)
        # print('\n\n', v1, v2, dv, dv < 1e-6, '\n')
        
        return dv < 1e-6

    @abstractmethod
    def perform_travel(self, action : TravelAction, t : Union[int, float]) -> tuple:
        """
        Performs a travel action

        ### Arguments:
            - action (:obj:`TravelAction`): travel action to be performed
            - t (`int` or `double`): current simulation time in [s]
        
        ### Returns:
            - status (`str`): action completion status
            - dt (`float`): time to be waited by the agent
        """
        pass
    
    @abstractmethod
    def perform_maneuver(self, action : ManeuverAction, t : Union[int, float]) -> tuple:
        """
        Performs a meneuver action

        ### Arguments:
            - action (:obj:`ManeuverAction`): maneuver action to be performed
            - t (`int` or `double`): current simulation time in [s]
        
        ### Returns:
            - status (`str`): action completion status
            - dt (`float`): time to be waited by the agent
        """
        pass

    def __repr__(self) -> str:
        return str(self.to_dict())

    def __str__(self):
        return str(dict(self.__dict__))
    
    def to_dict(self) -> dict:
        return dict(self.__dict__)

class GroundStationAgentState(SimulationAgentState):
    """
    Describes the state of a Ground Station Agent
    """
    def __init__(self, 
                lat: float, 
                lon: float,
                alt: float, 
                status: str = SimulationAgentState.IDLING, 
                pos : list = None,
                vel : list = None,
                t: Union[float, int] = 0, **_) -> None:
        
        self.lat = lat
        self.lon = lon
        self.alt = alt 

        R = 6.3781363e+003 + alt
        pos = [
                R * np.cos( lat * np.pi / 180.0) * np.cos( lon * np.pi / 180.0),
                R * np.cos( lat * np.pi / 180.0) * np.sin( lon * np.pi / 180.0),
                R * np.sin( lat * np.pi / 180.0)
        ]
        vel = [0, 0, 0]
        
        super().__init__(SimulationAgentTypes.GROUND_STATION.value, 
                        pos, 
                        vel, 
                        None, 
                        status, 
                        t)

    def propagate(self, _: Union[int, float]) -> tuple:
        # agent does not move
        return self.pos, self.vel

    def is_failure(self) -> None:
        # agent never fails
        return False

    def perform_travel(self, action: TravelAction, _: Union[int, float]) -> tuple:
        # agent cannot travel
        return action.ABORTED, 0.0

    def perform_maneuver(self, action: ManeuverAction, _: Union[int, float]) -> tuple:
        # agent cannot maneuver
        return action.ABORTED, 0.0


class SatelliteAgentState(SimulationAgentState):
    """
    Describes the state of a Satellite Agent
    """
    def __init__( self, 
                    orbit_state : dict,
                    time_step : float = None,
                    eps : float = None,
                    pos : list = None,
                    vel : list = None,
                    keplerian_state : dict = None,
                    t: Union[float, int] = 0.0, 
                    eclipse : int = 0,
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    **_
                ) -> None:
        
        self.orbit_state = orbit_state
        self.eclipse = eclipse
        if pos is None and vel is None:
            orbit_state : OrbitState = OrbitState.from_dict(self.orbit_state)
            cartesian_state = orbit_state.get_cartesian_earth_centered_inertial_state()
            pos = cartesian_state[0:3]
            vel = cartesian_state[3:]

            keplerian_state = orbit_state.get_keplerian_earth_centered_inertial_state()
            self.keplerian_state = {"aop" : keplerian_state.aop,
                                    "ecc" : keplerian_state.ecc,
                                    "sma" : keplerian_state.sma,
                                    "inc" : keplerian_state.inc,
                                    "raan" : keplerian_state.raan,
                                    "ta" : keplerian_state.ta}
        
        elif keplerian_state is not None:
            self.keplerian_state = keplerian_state
        
        self.time_step = time_step
        if eps:
            self.eps = eps
        else:
            self.eps = self.calc_eps(pos) if self.time_step else 1e-6
        
        super().__init__(   SimulationAgentTypes.SATELLITE.value, 
                            pos, 
                            vel, 
                            engineering_module, 
                            status, 
                            t)

    def propagate(self, tf: Union[int, float], update_keplerian : bool = True) -> tuple:
        # propagates orbit
        dt = tf - self.t
        if abs(dt) < 1e-6:
            return self.pos, self.vel

        # form the propcov.Spacecraft object
        attitude = propcov.NadirPointingAttitude()
        interp = propcov.LagrangeInterpolator()

        # following snippet is required, because any copy, changes to the propcov objects in the input spacecraft is reflected outside the function.
        spc_date = propcov.AbsoluteDate()
        orbit_state : OrbitState = OrbitState.from_dict(self.orbit_state)
        spc_date.SetJulianDate(orbit_state.date.GetJulianDate())
        spc_orbitstate = orbit_state.state
        
        spc = propcov.Spacecraft(spc_date, spc_orbitstate, attitude, interp, 0, 0, 0, 1, 2, 3) # TODO: initialization to the correct orientation of spacecraft is not necessary for the purpose of orbit-propagation, so ignored for time-being.
        start_date = spc_date

        # following snippet is required, because any copy, changes to the input start_date is reflected outside the function. (Similar to pass by reference in C++.)
        # so instead a separate copy of the start_date is made and is used within this function.
        _start_date = propcov.AbsoluteDate()
        _start_date.SetJulianDate(start_date.GetJulianDate())

        # form the propcov.Propagator object
        prop = propcov.Propagator(spc)

        # propagate to the specified start date since the date at which the orbit-state is defined
        # could be different from the specified start_date (propagation could be either forwards or backwards)
        prop.Propagate(_start_date)
        
        date = _start_date

        if self.time_step:
            # TODO compute dt as a multiple of the registered time-step 
            pass

        date.Advance(tf)
        prop.Propagate(date)
        
        cartesian_state = spc.GetCartesianState().GetRealArray()
        pos = cartesian_state[0:3]
        vel = cartesian_state[3:]

        if update_keplerian:
            keplerian_state = spc.GetKeplerianState().GetRealArray()
            self.keplerian_state = {"sma" : keplerian_state[0],
                                    "ecc" : keplerian_state[1],
                                    "inc" : keplerian_state[2],
                                    "raan" : keplerian_state[3],
                                    "aop" : keplerian_state[4],
                                    "ta" : keplerian_state[5]}                                
       
        return pos, vel

    def is_failure(self) -> None:
        if self.engineering_module:
            # agent only fails if internal components fail
            return self.engineering_module.is_failure()
        return False

    def perform_travel(self, action: TravelAction, t: Union[int, float]) -> tuple:
        # update state
        self.update_state(t, status=self.TRAVELING)

        # check if position was reached
        if self.comp_vectors(self.pos, action.final_pos):
            # if reached, return successful completion status
            return action.COMPLETED, 0.0
        else:
            # else, wait until position is reached
            dt = self.time_step if self.time_step else 60.0
            return action.PENDING, dt

    def perform_maneuver(self, action: ManeuverAction, t: Union[int, float]) -> tuple:
        # update state
        self.update_state(t, status=self.MANEUVERING)

        if self.engineering_module:
            # instruct engineering module to perform maneuver
            return self.engineering_module.perform_action(action, t)
        
        else:
            # satellite has no engineering modue and cannot perform attitude maneuver
            return action.ABORTED, 0.0
            
    def calc_eps(self, init_pos : list):
        """
        Calculates tolerance for position vector comparisons
        """

        # form the propcov.Spacecraft object
        attitude = propcov.NadirPointingAttitude()
        interp = propcov.LagrangeInterpolator()

        # following snippet is required, because any copy, changes to the propcov objects in the input spacecraft is reflected outside the function.
        spc_date = propcov.AbsoluteDate()
        orbit_state : OrbitState = OrbitState.from_dict(self.orbit_state)
        spc_date.SetJulianDate(orbit_state.date.GetJulianDate())
        spc_orbitstate = orbit_state.state
        
        spc = propcov.Spacecraft(spc_date, spc_orbitstate, attitude, interp, 0, 0, 0, 1, 2, 3) # TODO: initialization to the correct orientation of spacecraft is not necessary for the purpose of orbit-propagation, so ignored for time-being.
        start_date = spc_date

        # following snippet is required, because any copy, changes to the input start_date is reflected outside the function. (Similar to pass by reference in C++.)
        # so instead a separate copy of the start_date is made and is used within this function.
        _start_date = propcov.AbsoluteDate()
        _start_date.SetJulianDate(start_date.GetJulianDate())

        # form the propcov.Propagator object
        prop = propcov.Propagator(spc)

        # propagate to the specified start date since the date at which the orbit-state is defined
        # could be different from the specified start_date (propagation could be either forwards or backwards)
        prop.Propagate(_start_date)
        
        date = _start_date
        date.Advance(self.time_step)
        prop.Propagate(date)
        
        cartesian_state = spc.GetCartesianState().GetRealArray()
        pos = cartesian_state[0:3]

        dx = init_pos[0] - pos[0]
        dy = init_pos[1] - pos[1]
        dz = init_pos[2] - pos[2]

        return np.sqrt(dx**2 + dy**2 + dz**2) / 2.0
    
    def comp_vectors(self, v1 : list, v2 : list):
        """
        compares two vectors
        """
        dx = v1[0] - v2[0]
        dy = v1[1] - v2[1]
        dz = v1[2] - v2[2]

        dv = np.sqrt(dx**2 + dy**2 + dz**2)

        # print( '\n\n', v1, v2, dv, self.eps, dv < self.eps, '\n')
        
        return dv < self.eps

class UAVAgentState(SimulationAgentState):
    """
    Describes the state of a UAV Agent
    """
    def __init__(self, 
                    pos: list, 
                    vel: list, 
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    t: Union[float, int] = 0, 
                    **_
                ) -> None:
        super().__init__(pos, vel, engineering_module, status, t, **_)