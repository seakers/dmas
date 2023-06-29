
import numpy as np
from typing import Union
from nodes.agent import SimulationAgentState, SimulationAgentTypes
from nodes.engineering.engineering import EngineeringModule
from dmas.agents import AgentAction
from orbitpy.util import OrbitState
from orbitpy.propagator import J2AnalyticalPropagator
import propcov

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

    def perform_travel(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot travel
        return action.ABORTED, 0.0

    def perform_maneuver(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot maneuver
        return action.ABORTED, 0.0


class SatelliteAgentState(SimulationAgentState):
    """
    Describes the state of a Satellite Agent
    """
    def __init__( self, 
                    # # data_dir : str, 
                    orbit_state : dict,
                    pos : list = None,
                    vel : list = None,
                    # keplerian_state : dict = None,
                    t: Union[float, int] = 0.0, 
                    eclipse : int = 0,
                    engineering_module: EngineeringModule = None, 
                    status: str = ..., 
                    **_
                ) -> None:
        
        self.orbit_state = orbit_state

        if pos is None and vel is None:
            orbit_state : OrbitState = OrbitState.from_dict(self.orbit_state)
            cartesian_state = orbit_state.get_cartesian_earth_centered_inertial_state()
            pos = cartesian_state[0:3]
            vel = cartesian_state[3:]


            # keplerian_state = orbit_state.get_keplerian_earth_centered_inertial_state()
            # self.keplerian_state = {"aop" : keplerian_state.aop,
            #                         "ecc" : keplerian_state.ecc,
            #                         "sma" : keplerian_state.sma,
            #                         "inc" : keplerian_state.inc,
            #                         "raan" : keplerian_state.raan,
            #                         "ta" : keplerian_state.ta}
        
        # elif keplerian_state is not None:
        #     self.keplerian_state = keplerian_state
        
        super().__init__(   SimulationAgentTypes.SATELLITE.value, 
                            pos, 
                            vel, 
                            engineering_module, 
                            status, 
                            t)
        
        self.eclipse = eclipse

    def propagate(self, t: Union[int, float]) -> tuple:
        # propagates orbit
        if abs(self.t - t) < 1e-6:
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
        dt = t - self.t
        date.Advance(dt)
        prop.Propagate(date)
        
        cartesian_state = spc.GetCartesianState().GetRealArray()
        pos = cartesian_state[0:3]
        vel = cartesian_state[3:]

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

    def perform_travel(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot travel
        return action.ABORTED, 0.0

    def perform_maneuver(action: AgentAction, t: Union[int, float]) -> tuple:
        # agent cannot maneuver
        return action.ABORTED, 0.0

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