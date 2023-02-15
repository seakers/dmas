import json
from copy import deepcopy

with open('./utils/base_sat.json', 'r') as openfile:
    base_satellite = json.load(openfile)

satellites = []
r = 2; # number of planes
s = 2; # number of satellites per plane
re = 6378
altitude = 500
ecc = 0.01
inc = 67
argper = 0.0
for m in range(r):
    for n in range(s):
        new_satellite = {}
        new_satellite = base_satellite.copy()
        new_satellite["@id"] = "imaging_sat_"+str(m)+"_"+str(n)
        new_satellite["name"] = "imaging_sat_"+str(m)+"_"+str(n)
        pu = 360 / (r*s)
        delAnom = pu * r
        delRAAN = pu * s
        RAAN = delRAAN * m
        f = 1
        phasing = pu * f
        
        anom = (n * delAnom + phasing * m)
        new_satellite["orbitState"]["state"]["sma"] = altitude+re
        new_satellite["orbitState"]["state"]["ecc"] = ecc
        new_satellite["orbitState"]["state"]["inc"] = inc
        new_satellite["orbitState"]["state"]["raan"] = RAAN
        new_satellite["orbitState"]["state"]["aop"] = argper
        new_satellite["orbitState"]["state"]["ta"] = anom
        satellites.append(deepcopy(new_satellite))
json_object = json.dumps(satellites, indent=4)
 
# Writing to sample.json
with open("./utils/constellation.json", "w") as outfile:
    outfile.write(json_object)
        

