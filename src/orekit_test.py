'''
    TEST SCRIPT FOR LIBRARY IMPORTS
'''
import orekit
vm = orekit.initVM()

from orekit import JArray_double
from orekit.pyhelpers import setup_orekit_curdir

setup_orekit_curdir("./src/orekit/orekit-data.zip")   # orekit-data.zip shall be in current dir

from org.orekit.orbits import KeplerianOrbit, PositionAngle
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.utils import Constants, IERSConventions
from org.orekit.frames import FramesFactory
from org.orekit.bodies import OneAxisEllipsoid, CelestialBodyFactory
from math import radians, degrees
import pandas as pd

utc = TimeScalesFactory.getUTC()

ra = 500 * 1000         #  Apogee
rp = 400 * 1000         #  Perigee
i = radians(87.0)       # inclination
omega = radians(20.0)   # perigee argument
raan = radians(10.0)    # right ascension of ascending node
lv = radians(0.0)       # True anomaly

epochDate = AbsoluteDate(2020, 1, 1, 0, 0, 00.000, utc)
initial_date = epochDate

a = (rp + ra + 2 * Constants.WGS84_EARTH_EQUATORIAL_RADIUS) / 2.0
e = 1.0 - (rp + Constants.WGS84_EARTH_EQUATORIAL_RADIUS) / a

## Inertial frame where the satellite is defined
inertialFrame = FramesFactory.getEME2000()

## Orbit construction as Keplerian
initialOrbit = KeplerianOrbit(a, e, i, omega, raan, lv,
                              PositionAngle.TRUE,
                              inertialFrame, epochDate, Constants.WGS84_EARTH_MU)

propagator = KeplerianPropagator(initialOrbit)

ITRF = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                         Constants.WGS84_EARTH_FLATTENING,
                         ITRF)
sun = CelestialBodyFactory.getSun()
sunRadius = 696000000.0

from org.orekit.propagation.events import EclipseDetector, EventsLogger
from org.orekit.propagation.events.handlers import ContinueOnEvent

eclipse_detector = EclipseDetector(sun, sunRadius, earth).withUmbra().withHandler(ContinueOnEvent())

logger = EventsLogger()
logged_detector = logger.monitorDetector(eclipse_detector)

propagator.addEventDetector(logged_detector)

state = propagator.propagate(initial_date, initial_date.shiftedBy(3600.0 * 24))

events = logger.getLoggedEvents()
print(events.size())

start_time = -1
result = []

for event in logger.getLoggedEvents():

    if not event.isIncreasing():
        start_time = event.getState().getDate()
    elif start_time:
        stop_time = event.getState().getDate()
        duration = stop_time.durationFrom(start_time) / 60
        print(start_time, stop_time, duration)
        # result = result.append([start_time, stop_time])
# print(result)